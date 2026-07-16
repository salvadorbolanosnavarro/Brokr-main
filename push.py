# =============================================================================
# Broquer · push.py — Notificaciones a la app de iOS (APNs)
# -----------------------------------------------------------------------------
# Qué hace: cuando un prospecto escribe por WhatsApp, este módulo le manda la
# notificación al celular del agente. Habla directo con Apple (APNs), sin
# Firebase ni servicios de terceros.
#
# Mismos patrones del resto del repo: httpx async, Supabase por REST.
#
# VARIABLES DE ENTORNO (Railway → Variables):
#   APNS_KEY_P8     contenido COMPLETO del archivo AuthKey_XXXXXXXXXX.p8
#                   (pégalo tal cual, con sus saltos de línea)
#   APNS_KEY_ID     los 10 caracteres del nombre del archivo (AuthKey_ESTO.p8)
#   APNS_TEAM_ID    tu Team ID de Apple Developer (10 caracteres)
#   APNS_BUNDLE_ID  com.broquer.app
#   APNS_ENV        "prod" para App Store/TestFlight · "sandbox" para Xcode
#
# Si falta cualquiera, este módulo simplemente no hace nada y lo dice en el log.
# Nada más se rompe: WhatsApp sigue funcionando igual.
# =============================================================================

import os
import json
import time
import logging

import httpx

log = logging.getLogger("broquer.push")

APNS_KEY_P8    = os.environ.get("APNS_KEY_P8", "").replace("\\n", "\n").strip()
APNS_KEY_ID    = os.environ.get("APNS_KEY_ID", "").strip()
APNS_TEAM_ID   = os.environ.get("APNS_TEAM_ID", "").strip()
APNS_BUNDLE_ID = os.environ.get("APNS_BUNDLE_ID", "com.broquer.app").strip()
APNS_ENV       = os.environ.get("APNS_ENV", "prod").strip().lower()

APNS_HOST = ("https://api.sandbox.push.apple.com" if APNS_ENV.startswith("sand")
             else "https://api.push.apple.com")

SUPABASE_URL         = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY    = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_ANON_KEY


def push_configurado() -> bool:
    return bool(APNS_KEY_P8 and APNS_KEY_ID and APNS_TEAM_ID and APNS_BUNDLE_ID)


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
            {"iss": APNS_TEAM_ID, "iat": ahora},
            APNS_KEY_P8,
            algorithm="ES256",
            headers={"kid": APNS_KEY_ID, "alg": "ES256"},
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
# Supabase (REST, mismo patrón de whatsapp.py)
# -----------------------------------------------------------------------------
def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


async def _tokens_del_agente(user_id: str) -> list[str]:
    """Los device tokens de iOS del agente. Hoy guardamos uno por usuario
    (usuarios.apns_token); la firma devuelve lista para que el día que tenga
    iPhone + iPad no haya que tocar nada más."""
    if not SUPABASE_URL:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/usuarios",
                headers=_sb_headers(),
                params={"id": f"eq.{user_id}", "select": "apns_token"},
            )
        if r.status_code != 200:
            return []
        filas = r.json() or []
        return [f["apns_token"] for f in filas if f.get("apns_token")]
    except Exception as e:
        log.warning("APNs: no se pudieron leer los tokens de %s: %s", user_id, e)
        return []


async def _borrar_token(token: str):
    """Apple responde 410 cuando el agente desinstaló la app o reinstaló.
    Ese token ya no sirve nunca más: se limpia para no seguir intentando."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.patch(
                f"{SUPABASE_URL}/rest/v1/usuarios",
                headers={**_sb_headers(), "Prefer": "return=minimal"},
                params={"apns_token": f"eq.{token}"},
                json={"apns_token": None},
            )
    except Exception:
        pass


# -----------------------------------------------------------------------------
# El envío
# -----------------------------------------------------------------------------
async def enviar_push(user_id: str, titulo: str, cuerpo: str,
                      datos: dict | None = None, badge: int | None = None) -> bool:
    """Manda una notificación al iPhone del agente. Nunca lanza excepción:
    si algo falla, lo deja en el log y regresa False. Un aviso que no llega
    no puede tumbar el webhook de WhatsApp."""
    if not push_configurado():
        log.info("APNs sin configurar (faltan variables) — no se envía push.")
        return False

    jwt_tok = _apns_jwt()
    if not jwt_tok:
        return False

    tokens = await _tokens_del_agente(user_id)
    if not tokens:
        return False   # el agente no tiene la app de iOS instalada: normal

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

    headers = {
        "authorization": f"bearer {jwt_tok}",
        "apns-topic": APNS_BUNDLE_ID,
        "apns-push-type": "alert",
        "apns-priority": "10",
        "apns-expiration": str(int(time.time()) + 3600),
    }

    ok = False
    try:
        # http2=True es obligatorio: APNs no acepta HTTP/1.1.
        async with httpx.AsyncClient(http2=True, timeout=10) as c:
            for tok in tokens:
                try:
                    r = await c.post(f"{APNS_HOST}/3/device/{tok}",
                                     headers=headers, content=json.dumps(payload))
                    if r.status_code == 200:
                        ok = True
                    elif r.status_code == 410:
                        log.info("APNs: token muerto, se limpia.")
                        await _borrar_token(tok)
                    else:
                        log.warning("APNs %s: %s", r.status_code, r.text[:200])
                except Exception as e:
                    log.warning("APNs: fallo al enviar: %s", e)
    except Exception as e:
        log.error("APNs: no se pudo abrir conexión HTTP/2 "
                  "(¿falta instalar h2? revisa requirements.txt): %s", e)
    return ok


async def avisar_mensaje_whatsapp(user_id: str, nombre: str, texto: str,
                                  conversation_id: str, badge: int | None = None):
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
