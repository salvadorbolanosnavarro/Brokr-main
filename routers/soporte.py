"""Formulario de soporte.

El botón «Contactar soporte» era un enlace mailto:, y a quien no tiene un
programa de correo configurado (muy común en Windows o en un navegador
prestado) simplemente no le hacía nada. Ahora abre un formulario dentro de
Broquer: el usuario escribe su mensaje, adjunta una imagen si quiere, y el
servidor lo manda a soporte por Resend con sus datos de cuenta ya incluidos.
La respuesta de soporte le llega a su correo (reply_to).
"""
from __future__ import annotations

import base64
import html
import logging
import time
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from core.auth import require_user_id
from core.config import settings
from core.database import get_rows
from core.organizations import get_org_id_for_user

log = logging.getLogger("soporte")
router = APIRouter()

SOPORTE_EMAIL = "hola@broquer.app"
MAX_MENSAJE = 5000
MAX_IMAGEN = 5 * 1024 * 1024
TIPOS_IMAGEN = {
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
    "image/gif": "gif", "image/heic": "heic", "image/heif": "heif",
}
# Límite sencillo por usuario para que un doble clic o un script no llene la
# bandeja de soporte.
MAX_POR_HORA = 5
_envios: Dict[str, List[float]] = {}


def _cupo(user_id: str, ahora: Optional[float] = None) -> bool:
    ahora = time.time() if ahora is None else ahora
    recientes = [t for t in _envios.get(user_id, []) if ahora - t < 3600]
    if len(recientes) >= MAX_POR_HORA:
        _envios[user_id] = recientes
        return False
    recientes.append(ahora)
    _envios[user_id] = recientes
    return True


async def _primera(tabla: str, params: dict) -> dict:
    try:
        filas = await get_rows(tabla, {**params, "limit": "1"}, timeout=10)
        return filas[0] if filas else {}
    except Exception as e:
        log.warning("soporte: no se pudo leer %s: %s", tabla, e)
        return {}


async def datos_de_cuenta(user_id: str) -> Dict[str, str]:
    """Lo que soporte necesita para ubicar la cuenta sin preguntarle nada."""
    usuario = await _primera("usuarios", {"id": f"eq.{user_id}", "select": "*"})
    perfil = await _primera("perfiles", {"user_id": f"eq.{user_id}", "select": "*"})
    org_nombre = ""
    try:
        org_id = await get_org_id_for_user(user_id)
    except Exception:
        org_id = None
    if org_id:
        org_nombre = (await _primera("organizaciones", {"id": f"eq.{org_id}", "select": "nombre"})).get("nombre") or ""
    nombre = (perfil.get("nombre") or perfil.get("nombre_publico") or usuario.get("nombre") or "").strip()
    return {
        "user_id": user_id,
        "nombre": nombre,
        "email": (usuario.get("email") or perfil.get("email") or "").strip(),
        "telefono": str(perfil.get("telefono") or usuario.get("telefono") or "").strip(),
        "plan": str(usuario.get("plan") or usuario.get("rol") or "").strip(),
        "organizacion": org_nombre.strip(),
    }


def armar_correo(cuenta: Dict[str, str], mensaje: str, pagina: str, dispositivo: str) -> Tuple[str, str]:
    e = lambda v: html.escape(str(v or ""))  # noqa: E731
    quien = cuenta.get("nombre") or cuenta.get("email") or "Usuario"
    asunto = f"Soporte · {quien}"[:150]
    filas = [
        ("Nombre", cuenta.get("nombre")), ("Correo", cuenta.get("email")),
        ("Teléfono", cuenta.get("telefono")), ("Plan", cuenta.get("plan")),
        ("Empresa", cuenta.get("organizacion")), ("ID de usuario", cuenta.get("user_id")),
        ("Página", pagina), ("Dispositivo", dispositivo),
    ]
    tabla = "".join(
        f"<tr><td style='padding:4px 12px 4px 0;color:#666'>{e(k)}</td><td style='padding:4px 0'>{e(v)}</td></tr>"
        for k, v in filas if v
    )
    cuerpo = (
        "<div style='font-family:Arial,sans-serif;font-size:14px;color:#222'>"
        f"<p style='white-space:pre-wrap'>{e(mensaje)}</p>"
        "<hr style='border:none;border-top:1px solid #ddd;margin:16px 0'>"
        f"<table style='font-size:13px'>{tabla}</table></div>"
    )
    return asunto, cuerpo


@router.post("/soporte/mensaje")
async def enviar_mensaje(
    request: Request,
    mensaje: str = Form(...),
    pagina: str = Form(""),
    dispositivo: str = Form(""),
    imagen: Optional[UploadFile] = File(None),
):
    user_id = await require_user_id(request, detail="Inicia sesión para escribirle a soporte.")
    texto = (mensaje or "").strip()
    if len(texto) < 3:
        raise HTTPException(422, "Escribe tu mensaje.")
    if len(texto) > MAX_MENSAJE:
        raise HTTPException(422, f"El mensaje es muy largo (máximo {MAX_MENSAJE} caracteres).")

    adjuntos = []
    if imagen is not None and (imagen.filename or ""):
        tipo = (imagen.content_type or "").lower()
        if tipo not in TIPOS_IMAGEN:
            raise HTTPException(422, "La imagen debe ser JPG, PNG, WEBP, GIF o HEIC.")
        datos = await imagen.read(MAX_IMAGEN + 1)
        if len(datos) > MAX_IMAGEN:
            raise HTTPException(413, "La imagen pesa más de 5 MB.")
        if datos:
            adjuntos.append({"filename": f"captura.{TIPOS_IMAGEN[tipo]}",
                             "content": base64.b64encode(datos).decode()})

    if not settings.resend_api_key:
        raise HTTPException(503, f"No pudimos enviar tu mensaje. Escríbenos a {SOPORTE_EMAIL}.")
    if not _cupo(user_id):
        raise HTTPException(429, f"Ya nos enviaste varios mensajes. Si es urgente, escríbenos a {SOPORTE_EMAIL}.")

    cuenta = await datos_de_cuenta(user_id)
    asunto, cuerpo = armar_correo(cuenta, texto, pagina[:300], dispositivo[:300])
    payload = {"from": settings.resend_from, "to": [SOPORTE_EMAIL], "subject": asunto, "html": cuerpo}
    if cuenta.get("email"):
        payload["reply_to"] = cuenta["email"]
    if adjuntos:
        payload["attachments"] = adjuntos
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post("https://api.resend.com/emails",
                             headers={"Authorization": f"Bearer {settings.resend_api_key}",
                                      "Content-Type": "application/json"},
                             json=payload)
    except Exception as ex:
        log.warning("soporte: resend falló: %s", ex)
        raise HTTPException(502, f"No pudimos enviar tu mensaje. Escríbenos a {SOPORTE_EMAIL}.")
    if r.status_code not in (200, 201, 202):
        log.warning("soporte: resend -> %s %s", r.status_code, r.text[:300])
        raise HTTPException(502, f"No pudimos enviar tu mensaje. Escríbenos a {SOPORTE_EMAIL}.")
    return {"ok": True, "email": cuenta.get("email") or ""}
