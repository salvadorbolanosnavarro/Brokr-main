# =============================================================================
# Broquer · push.py — Notificaciones a la app de iOS (APNs)
# -----------------------------------------------------------------------------
# Qué hace: cuando un prospecto escribe por WhatsApp, este módulo le manda la
# notificación al celular del agente. Habla directo con Apple (APNs), sin
# Firebase ni servicios de terceros.
#
# La configuración vive en core.config y el acceso a Supabase en core.database.
# Si faltan credenciales de APNs, este módulo no envía nada y lo deja en el log;
# WhatsApp sigue funcionando igual.
# =============================================================================

import json
import logging
import time

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import get_rows, patch_rows

log = logging.getLogger("broquer.push")
router = APIRouter()

APNS_HOST = (
    "https://api.sandbox.push.apple.com"
    if settings.apns_env.startswith("sand")
    else "https://api.push.apple.com"
)


def push_configurado() -> bool:
    return bool(
        settings.apns_key_p8
        and settings.apns_key_id
        and settings.apns_team_id
        and settings.apns_bundle_id
    )


# -----------------------------------------------------------------------------
# Token de autorización de Apple (JWT ES256). Apple lo acepta hasta 1 hora;
# lo renovamos cada 45 min. Uno solo sirve para todos los envíos.
# -----------------------------------------------------------------------------
_jwt_cache = {"token": None, "iat": 0}


def _apns_jwt() -> str | None:
    ahora = int(time.time())
    if _jwt_cache["token"] and (ahora - _jwt_cache["iat"]) < 45 * 60:
        return _jwt_cache["token"]
    try:
        import jwt  # PyJWT

        tok = jwt.encode(
            {"iss": settings.apns_team_id, "iat": ahora},
            settings.apns_key_p8,
            algorithm="ES256",
            headers={"kid": settings.apns_key_id, "alg": "ES256"},
        )
        if isinstance(tok, bytes):
            tok = tok.decode()
        _jwt_cache["token"] = tok
        _jwt_cache["iat"] = ahora
        return tok
    except Exception as e:
        log.error("APNs: no se pudo firmar el token (revisa APNS_KEY_P8): %s", e)
        return None


# -----------------------------------------------------------------------------
# Supabase
# -----------------------------------------------------------------------------
async def _tokens_del_agente(user_id: str) -> list[str]:
    """Devuelve los device tokens de iOS del agente."""
    try:
        filas = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "apns_token"},
            timeout=10,
        )
        return [f["apns_token"] for f in filas if f.get("apns_token")]
    except Exception as e:
        log.warning("APNs: no se pudieron leer los tokens de %s: %s", user_id, e)
        return []


async def _borrar_token(token: str) -> None:
    """Limpia un token que Apple marcó como definitivamente inválido (410)."""
    try:
        await patch_rows(
            "usuarios",
            {"apns_token": f"eq.{token}"},
            {"apns_token": None},
            prefer="return=minimal",
            timeout=10,
        )
    except Exception:
        pass


# -----------------------------------------------------------------------------
# El envío
# -----------------------------------------------------------------------------
async def _enviar_a_tokens(tokens: list[str], payload: dict) -> list[dict]:
    """Manda el payload a cada token y regresa lo que Apple respondió por
    cada uno — es el detalle que /push/prueba necesita para diagnosticar
    (200 entregado, 400 BadDeviceToken → token de sandbox contra servidor
    de producción o viceversa, 403 topic/llave mal, 410 token muerto)."""
    jwt_tok = _apns_jwt()
    if not jwt_tok:
        return [{"token": t[-8:], "status": None, "detalle": "No se pudo firmar el JWT de APNs."} for t in tokens]

    headers = {
        "authorization": f"bearer {jwt_tok}",
        "apns-topic": settings.apns_bundle_id,
        "apns-push-type": "alert",
        "apns-priority": "10",
        "apns-expiration": str(int(time.time()) + 3600),
    }

    resultados = []
    try:
        # http2=True es obligatorio: APNs no acepta HTTP/1.1.
        async with httpx.AsyncClient(http2=True, timeout=10) as c:
            for tok in tokens:
                try:
                    r = await c.post(
                        f"{APNS_HOST}/3/device/{tok}",
                        headers=headers,
                        content=json.dumps(payload),
                    )
                    resultados.append({"token": tok[-8:], "status": r.status_code, "detalle": r.text[:200]})
                    if r.status_code == 410:
                        log.info("APNs: token muerto, se limpia.")
                        await _borrar_token(tok)
                    elif r.status_code != 200:
                        log.warning("APNs %s: %s", r.status_code, r.text[:200])
                except Exception as e:
                    log.warning("APNs: fallo al enviar: %s", e)
                    resultados.append({"token": tok[-8:], "status": None, "detalle": str(e)})
    except Exception as e:
        log.error(
            "APNs: no se pudo abrir conexión HTTP/2 "
            "(¿falta instalar h2? revisa requirements.txt): %s",
            e,
        )
        resultados = [{"token": t[-8:], "status": None, "detalle": "No se pudo conectar a APNs (¿falta h2?)."} for t in tokens]
    return resultados


def _armar_payload(titulo: str, cuerpo: str, datos: dict | None, badge: int | None) -> dict:
    payload = {
        "aps": {
            "alert": {"title": titulo, "body": cuerpo},
            "sound": "default",
            "thread-id": "broquer-wa",
        }
    }
    if badge is not None:
        payload["aps"]["badge"] = int(badge)
    if datos:
        payload.update(datos)
    return payload


async def enviar_push(
    user_id: str,
    titulo: str,
    cuerpo: str,
    datos: dict | None = None,
    badge: int | None = None,
) -> bool:
    """Manda una notificación al iPhone del agente sin tumbar al llamador."""
    if not push_configurado():
        log.info("APNs sin configurar (faltan variables) — no se envía push.")
        return False

    tokens = await _tokens_del_agente(user_id)
    if not tokens:
        return False

    payload = _armar_payload(titulo, cuerpo, datos, badge)
    resultados = await _enviar_a_tokens(tokens, payload)
    return any(r["status"] == 200 for r in resultados)


@router.get("/push/estado")
async def estado_push(request: Request) -> dict:
    """Diagnóstico rápido de por qué no llegan notificaciones, sin exponer
    ningún secreto (solo booleanos): ¿el servidor tiene APNs configurado?
    ¿este usuario ya tiene guardado el token de su iPhone? Con esto se
    puede saber de qué lado está el problema sin meterse a los logs de
    Railway ni a las variables de entorno."""
    uid = await get_user_id_from_token(request)
    if not uid:
        raise HTTPException(401, "Sesión inválida.")
    tokens = await _tokens_del_agente(uid)
    return {
        "apns_configurado": push_configurado(),
        "apns_env": settings.apns_env,
        "tiene_token_guardado": len(tokens) > 0,
    }


@router.post("/push/prueba")
async def prueba_push(request: Request) -> dict:
    """Manda una notificación de verdad al iPhone del usuario y regresa
    exactamente lo que respondió Apple por cada token guardado — para
    distinguir, sin logs de Railway, entre: token de sandbox contra
    servidor de producción (o al revés), token muerto, llave/topic mal
    configurados, o que sí se entregó y el problema está en los ajustes
    de notificaciones del propio iPhone."""
    uid = await get_user_id_from_token(request)
    if not uid:
        raise HTTPException(401, "Sesión inválida.")
    if not push_configurado():
        raise HTTPException(409, "APNs no está configurado en el servidor (faltan variables de entorno).")
    tokens = await _tokens_del_agente(uid)
    if not tokens:
        raise HTTPException(404, "No hay ningún token de iPhone guardado para este usuario.")

    payload = _armar_payload(
        "Prueba de Broquer",
        "Si ves esto, las notificaciones sí funcionan.",
        datos={"tipo": "prueba"},
        badge=None,
    )
    resultados = await _enviar_a_tokens(tokens, payload)
    return {
        "apns_env": settings.apns_env,
        "entregado_a_alguno": any(r["status"] == 200 for r in resultados),
        "resultados": resultados,
    }


async def avisar_mensaje_whatsapp(
    user_id: str,
    nombre: str,
    texto: str,
    conversation_id: str,
    badge: int | None = None,
) -> None:
    """Atajo con el copy ya listo para el caso de WhatsApp."""
    cuerpo = (texto or "").strip().replace("\n", " ")
    if len(cuerpo) > 140:
        cuerpo = cuerpo[:139] + "…"
    await enviar_push(
        user_id,
        titulo=nombre or "Nuevo mensaje",
        cuerpo=cuerpo or "Te escribió un prospecto por WhatsApp.",
        datos={"tipo": "whatsapp", "conversation_id": conversation_id},
        badge=badge,
    )
