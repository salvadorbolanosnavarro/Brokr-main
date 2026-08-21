"""Meta WhatsApp Cloud API transport and token-health handling."""
from __future__ import annotations

from datetime import datetime, timezone
import logging

import httpx

from routers.whatsapp_data import sb_patch

try:
    from push import enviar_push
except Exception:  # pragma: no cover
    async def enviar_push(*args, **kwargs):
        return False


log = logging.getLogger("broquer.whatsapp2")
GRAPH_API = "https://graph.facebook.com/v21.0"
WA_MAX_TEXTO = 4000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def revisar_token(numero: dict, err: dict | None) -> None:
    if not err or err.get("code") not in (190, 102):
        return
    numero_id = numero.get("id")
    if not numero_id:
        return
    try:
        if numero.get("token_valido") is False:
            return
        await sb_patch(
            "wa2_numeros",
            {"id": f"eq.{numero_id}"},
            {"token_valido": False, "token_error_at": _now(), "ia_enabled": False},
        )
        numero["token_valido"] = False
        await enviar_push(
            numero.get("user_id"),
            "Tu WhatsApp se desconectó",
            "Meta dejó de aceptar la conexión de tu número. Entra a WhatsApp en "
            "Broquer y vuelve a apretar 'Conectar número' para reactivarlo.",
            datos={"tipo": "whatsapp"},
        )
        log.error(
            "Token inválido para el número %s (user %s): %s",
            numero.get("phone_number_id"),
            numero.get("user_id"),
            err.get("message"),
        )
    except Exception as exc:  # pragma: no cover
        log.warning("No se pudo marcar el token inválido de %s: %s", numero_id, exc)


async def send_text_detallado(numero: dict, wa_id: str, texto: str) -> tuple[str | None, dict | None]:
    if not numero.get("access_token"):
        return None, {"code": None, "message": "Este número no tiene un token de acceso válido."}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{GRAPH_API}/{numero['phone_number_id']}/messages",
            headers={"Authorization": f"Bearer {numero['access_token']}"},
            json={
                "messaging_product": "whatsapp",
                "to": wa_id,
                "type": "text",
                "text": {"body": texto, "preview_url": False},
            },
        )
        if response.status_code >= 400:
            log.error("Envío de texto falló (%s): %s", numero["phone_number_id"], response.text[:300])
            try:
                err = response.json().get("error") or {}
            except Exception:
                err = {}
            detalle = {
                "code": err.get("code"),
                "message": err.get("message") or "No se pudo enviar el mensaje.",
            }
            await revisar_token(numero, detalle)
            return None, detalle
        data = response.json()
        messages = data.get("messages") or []
        return (messages[0].get("id") if messages else None), None


async def send_text(numero: dict, wa_id: str, texto: str) -> str | None:
    texto = (texto or "").strip()
    if not texto:
        return None
    if len(texto) <= WA_MAX_TEXTO:
        wamid, _ = await send_text_detallado(numero, wa_id, texto)
        return wamid
    partes, actual = [], ""
    for parrafo in texto.split("\n"):
        if len(actual) + len(parrafo) + 1 > WA_MAX_TEXTO:
            if actual:
                partes.append(actual)
            actual = parrafo[:WA_MAX_TEXTO]
        else:
            actual = (actual + "\n" + parrafo) if actual else parrafo
    if actual:
        partes.append(actual)
    ultimo = None
    for parte in partes:
        ultimo, _ = await send_text_detallado(numero, wa_id, parte)
    return ultimo


async def marcar_leido(numero: dict, wamid: str | None, escribiendo: bool = True) -> None:
    if not wamid or not numero.get("access_token"):
        return
    cuerpo = {"messaging_product": "whatsapp", "status": "read", "message_id": wamid}
    if escribiendo:
        cuerpo["typing_indicator"] = {"type": "text"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                headers={"Authorization": f"Bearer {numero['access_token']}"},
                json=cuerpo,
            )
    except Exception as exc:
        log.debug("No se pudo marcar como leído: %s", exc)


async def descargar_media(numero: dict, media_id: str) -> tuple[bytes | None, str]:
    if not media_id or not numero.get("access_token"):
        return None, ""
    headers = {"Authorization": f"Bearer {numero['access_token']}"}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(f"{GRAPH_API}/{media_id}", headers=headers)
            if response.status_code >= 400:
                log.warning("No se pudo obtener la media %s: %s", media_id, response.text[:200])
                return None, ""
            info = response.json()
            url, mime = info.get("url"), info.get("mime_type") or ""
            if not url:
                return None, ""
            binary = await client.get(url, headers=headers)
            if binary.status_code >= 400 or not binary.content:
                return None, ""
            return binary.content, mime
    except Exception as exc:
        log.warning("Error bajando media %s: %s", media_id, exc)
        return None, ""
