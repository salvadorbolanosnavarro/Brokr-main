"""Comentarios urgentes de supervisión (Broquer para Empresas).

El dueño o un admin de la empresa deja, en la bitácora de un cliente, una nota
marcada como URGENTE para el agente que lo lleva. Al agente le llega un push,
la ve en el apartado "Urgente de supervisión" de Clientes (con contador en el
menú) y la marca como atendida; el supervisor ve cuáles siguen pendientes.

Por qué pasa por aquí y no directo desde el navegador: las columnas urgente /
para_usuario / atendido_* de actividades tienen un candado en Postgres
(sql-manual/20261013-supervision-urgente.sql) que solo deja escribirlas con
service key. Aquí se revisa quién pide: crear solo owner/admin; dar por
atendido solo el agente destinatario o un admin de la misma empresa.

Si la migración aún no se corrió, leer devuelve listas vacías (la pantalla
simplemente no muestra el apartado) y crear responde 503 con la instrucción.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import require_user_id
from core.database import get_rows, patch_rows, post_rows
from routers.organizaciones import get_org_context

router = APIRouter()
log = logging.getLogger("broquer.supervision")

_ID_SEGURO = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ROLES_SUPERVISOR = ("owner", "admin")
MAX_TEXTO = 4000
MAX_ADJUNTOS = 20
MAX_LISTA = 100
FALTA_MIGRACION = ("Falta activar los comentarios urgentes: corre "
                   "sql-manual/20261013-supervision-urgente.sql en Supabase.")


class ComentarioReq(BaseModel):
    contacto_id: str
    texto: str = ""
    adjuntos: list[Any] = []
    propiedad_id: Optional[str] = None


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _es_supervisor(ctx: Optional[dict]) -> bool:
    return bool(ctx and ctx.get("activo") and ctx.get("org_id")
                and ctx.get("rol_org") in _ROLES_SUPERVISOR)


async def _miembro_activo(org_id: str, user_id: str) -> bool:
    if not org_id or not user_id:
        return False
    filas = await get_rows("organizacion_miembros", {
        "org_id": f"eq.{org_id}", "user_id": f"eq.{user_id}", "activo": "eq.true",
        "select": "user_id", "limit": "1"})
    return bool(filas)


async def _nombres(ids: set[str]) -> dict[str, str]:
    ids = {i for i in ids if i and _ID_SEGURO.match(str(i))}
    if not ids:
        return {}
    try:
        filas = await get_rows("usuarios", {"id": f"in.({','.join(sorted(ids))})", "select": "id,nombre,email"})
    except Exception:
        return {}
    return {f["id"]: (f.get("nombre") or f.get("email") or "Alguien del equipo") for f in filas}


async def _clientes(ids: set[str]) -> dict[str, str]:
    ids = {str(i) for i in ids if i and _ID_SEGURO.match(str(i))}
    if not ids:
        return {}
    try:
        filas = await get_rows("contactos", {"id": f"in.({','.join(sorted(ids))})", "select": "id,nombre"})
    except Exception:
        return {}
    return {str(f["id"]): (f.get("nombre") or "Sin nombre") for f in filas}


async def _avisar(para: str, autor: str, cliente: str, texto: str, contacto_id: str) -> None:
    try:
        from push import enviar_push
        cuerpo = f"{autor} sobre {cliente}: {texto}" if texto else f"{autor} dejó un comentario sobre {cliente}."
        await enviar_push(para, "Urgente de supervisión", cuerpo[:180],
                          {"tipo": "supervision", "contacto_id": contacto_id})
    except Exception:
        log.warning("No se pudo mandar el push de supervisión", exc_info=True)


@router.post("/supervision/comentarios")
async def crear_comentario(body: ComentarioReq, request: Request):
    user_id = await require_user_id(request, detail="Inicia sesión.")
    ctx = await get_org_context(user_id)
    if not _es_supervisor(ctx):
        raise HTTPException(status_code=403,
                            detail="Solo el dueño o un admin de la empresa puede dejar comentarios urgentes.")
    org_id = ctx["org_id"]

    contacto_id = (body.contacto_id or "").strip()
    if not _ID_SEGURO.match(contacto_id):
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")
    propiedad_id = (body.propiedad_id or "").strip() or None
    if propiedad_id and not _ID_SEGURO.match(propiedad_id):
        raise HTTPException(status_code=400, detail="Inmueble no válido.")
    texto = (body.texto or "").strip()[:MAX_TEXTO]
    adjuntos = body.adjuntos if isinstance(body.adjuntos, list) else []
    if len(adjuntos) > MAX_ADJUNTOS:
        raise HTTPException(status_code=400, detail="Demasiados adjuntos.")
    if not texto and not adjuntos:
        raise HTTPException(status_code=400, detail="Escribe el comentario.")

    filas = await get_rows("contactos", {
        "id": f"eq.{contacto_id}", "select": "id,nombre,org_id,user_id,asignado_a", "limit": "1"})
    if not filas:
        raise HTTPException(status_code=404, detail="Ese cliente ya no existe.")
    c = filas[0]
    misma_org = c.get("org_id") == org_id or (
        not c.get("org_id") and await _miembro_activo(org_id, c.get("user_id")))
    if not misma_org:
        raise HTTPException(status_code=403, detail="Ese cliente no es de tu empresa.")

    # El aviso va a quien lleva al cliente: el agente asignado o, si no hay,
    # quien lo dio de alta. Nunca a uno mismo ni a alguien fuera del equipo.
    para = c.get("asignado_a") or c.get("user_id")
    if not para or para == user_id:
        raise HTTPException(status_code=400,
                            detail="Asigna primero este cliente a un agente para poder mandarle un comentario urgente.")
    if not await _miembro_activo(org_id, para):
        raise HTTPException(status_code=400,
                            detail="El agente de este cliente ya no está activo en la empresa. Reasígnalo primero.")

    fila = {
        "user_id": user_id,
        "org_id": org_id,
        "contacto_id": contacto_id,
        "propiedad_id": propiedad_id,
        "tipo": "nota" if texto else "archivo",
        "texto": texto,
        "adjuntos": adjuntos,
        "urgente": True,
        "para_usuario": para,
    }
    try:
        creadas = await post_rows("actividades", fila)
    except Exception as exc:
        log.warning("No se pudo crear el comentario urgente: %s", exc)
        raise HTTPException(status_code=503, detail=FALTA_MIGRACION) from exc
    nueva = creadas[0] if creadas else fila

    autor = (await _nombres({user_id})).get(user_id, "Tu supervisor")
    await _avisar(para, autor, c.get("nombre") or "un cliente", texto, contacto_id)
    return {"ok": True, "actividad": nueva}


def _entrada(a: dict, nombres: dict[str, str], clientes: dict[str, str]) -> dict:
    return {
        "id": a.get("id"),
        "contacto_id": a.get("contacto_id"),
        "cliente": clientes.get(str(a.get("contacto_id")), "Cliente"),
        "texto": a.get("texto") or "",
        "creado_en": a.get("created_at"),
        "autor": nombres.get(a.get("user_id"), "Supervisor"),
        "para": nombres.get(a.get("para_usuario"), "Agente"),
        "para_usuario": a.get("para_usuario"),
    }


@router.get("/supervision/pendientes")
async def listar_pendientes(request: Request):
    """Lo que me toca atender y, si superviso, lo que el equipo aún no atiende."""
    user_id = await require_user_id(request, detail="Inicia sesión.")
    ctx = await get_org_context(user_id)
    es_sup = _es_supervisor(ctx)
    base = {"urgente": "eq.true", "atendido_en": "is.null",
            "select": "id,contacto_id,texto,created_at,user_id,para_usuario",
            "order": "created_at.desc", "limit": str(MAX_LISTA)}
    try:
        para_mi = await get_rows("actividades", {**base, "para_usuario": f"eq.{user_id}"})
        equipo = (await get_rows("actividades", {**base, "org_id": f"eq.{ctx['org_id']}",
                                                 "para_usuario": f"neq.{user_id}"})
                  if es_sup else [])
    except Exception:
        return {"para_mi": [], "del_equipo": [], "es_supervisor": es_sup, "activo": False}

    todas = para_mi + equipo
    nombres = await _nombres({a.get("user_id") for a in todas} | {a.get("para_usuario") for a in todas})
    clientes = await _clientes({a.get("contacto_id") for a in todas})
    return {
        "para_mi": [_entrada(a, nombres, clientes) for a in para_mi],
        "del_equipo": [_entrada(a, nombres, clientes) for a in equipo],
        "es_supervisor": es_sup,
        "activo": True,
    }


@router.get("/supervision/contador")
async def contar_pendientes(request: Request):
    user_id = await require_user_id(request, detail="Inicia sesión.")
    try:
        filas = await get_rows("actividades", {
            "urgente": "eq.true", "atendido_en": "is.null", "para_usuario": f"eq.{user_id}",
            "select": "id", "limit": str(MAX_LISTA)})
    except Exception:
        return {"pendientes": 0}
    return {"pendientes": len(filas)}


@router.post("/supervision/comentarios/{actividad_id}/atendido")
async def marcar_atendido(actividad_id: str, request: Request):
    user_id = await require_user_id(request, detail="Inicia sesión.")
    if not _ID_SEGURO.match(actividad_id or ""):
        raise HTTPException(status_code=404, detail="Ese comentario no existe.")
    try:
        filas = await get_rows("actividades", {
            "id": f"eq.{actividad_id}", "limit": "1",
            "select": "id,org_id,urgente,para_usuario,atendido_en,atendido_por"})
    except Exception as exc:
        raise HTTPException(status_code=503, detail=FALTA_MIGRACION) from exc
    if not filas or not filas[0].get("urgente"):
        raise HTTPException(status_code=404, detail="Ese comentario no existe.")
    a = filas[0]
    if a.get("atendido_en"):
        return {"ok": True, "atendido_en": a["atendido_en"], "atendido_por": a.get("atendido_por")}

    permitido = a.get("para_usuario") == user_id
    if not permitido:
        ctx = await get_org_context(user_id)
        permitido = _es_supervisor(ctx) and a.get("org_id") == ctx["org_id"]
    if not permitido:
        raise HTTPException(status_code=403, detail="Este comentario no es para ti.")

    cuando = _ahora()
    await patch_rows("actividades", {"id": f"eq.{actividad_id}", "atendido_en": "is.null"},
                     {"atendido_en": cuando, "atendido_por": user_id})
    return {"ok": True, "atendido_en": cuando, "atendido_por": user_id}
