# =============================================================================
# Broquer · Módulo WhatsApp 2.0 (multi-número + IA de recepción)
# -----------------------------------------------------------------------------
# Módulo construido DESDE CERO. No reutiliza código ni tablas de whatsapp.py.
# Vive en su propio prefijo /whatsapp2 y su propio set de tablas (wa2_*).
#
# Cómo llegan los mensajes de VARIOS números al MISMO webhook de este módulo,
# sin tocar el webhook del módulo viejo: Meta permite fijar un "callback URL"
# alterno por WABA con override_callback_uri al suscribir la app
# (POST /{waba_id}/subscribed_apps). Este módulo siempre se suscribe con ese
# override apuntando a /whatsapp2/webhook, así que los números conectados aquí
# jamás tocan el webhook de whatsapp.py y viceversa.
#
# Conectar en main.py:
#   from whatsapp2 import router as whatsapp2_router
#   app.include_router(whatsapp2_router)
# =============================================================================

import re
import json
import asyncio
import logging
import hmac
import hashlib
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows
from routers.whatsapp_stats import _agrega_ventana, _dt, _mediana
from routers.whatsapp_media_storage import borrar_archivos as _borrar_archivos, guardar_archivo as _guardar_archivo
_dt.__doc__ = "Parsea un timestamptz de Postgres a datetime con zona. Nunca revienta."
_agrega_ventana.__doc__ = "Todos los números de WhatsApp para una ventana de tiempo."

try:
    from push import enviar_push
except Exception:  # pragma: no cover — un push que falla no debe tumbar nada
    async def enviar_push(*a, **k):
        return False

try:
    from routers.organizaciones import get_org_context
except Exception:  # pragma: no cover — si el módulo de equipo no carga, cada quien ve solo lo suyo
    async def get_org_context(user_id):
        return None

log = logging.getLogger("broquer.whatsapp2")

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------

ANTHROPIC_API_KEY = settings.anthropic_api_key
ANTHROPIC_BASE    = settings.anthropic_base
WA2_MODEL         = settings.wa2_model

GRAPH_API       = "https://graph.facebook.com/v21.0"
META_APP_ID     = settings.wa2_meta_app_id
META_APP_SECRET = settings.wa2_meta_app_secret
WA2_VERIFY_TOKEN = settings.wa2_verify_token
# Es la MISMA app de Meta que se usa para el OAuth, así que la firma es la
# misma clave secreta. Si alguien no puso WA_APP_SECRET en Railway, caemos
# a META_APP_SECRET en vez de quedarnos sin verificar nada.
WA2_APP_SECRET   = settings.wa2_app_secret
WA2_REGISTER_PIN = settings.wa2_register_pin
# URL pública propia de este módulo (para el override_callback_uri al suscribir)
WA2_WEBHOOK_URL  = settings.wa2_webhook_url

BROQUER_API_BASE = settings.wa2_broquer_api_base
HISTORY_LIMIT = 16

# Zona horaria por defecto de todo el módulo. ESTA CONSTANTE FALTABA: el
# endpoint /whatsapp2/estadisticas la usaba sin que existiera en ningún lado,
# así que reventaba con NameError (error 500) en CUALQUIER llamada que no
# mandara ?zona=... — que es exactamente como la llama estadisticas.html.
# Resultado: la pestaña de WhatsApp en Estadísticas nunca funcionó.
_ZONA_DEFAULT = settings.wa2_zone_default

# Segundos que se espera antes de contestar, para AGRUPAR mensajes seguidos.
# En WhatsApp la gente no escribe un párrafo: escribe "hola", "busco casa",
# "en Altozano" en tres mensajes de tres segundos. Sin esto se disparaban tres
# respuestas de la IA en paralelo —incoherentes entre sí y pagando tres veces—
# y el prospecto veía a un bot atropellado. Con esto, solo el ÚLTIMO mensaje
# del ráfaga contesta, y contesta ya con los tres en el historial.
WA2_DEBOUNCE = settings.wa2_debounce_seconds

# WhatsApp corta los mensajes de texto en 4096 caracteres; arriba de eso Meta
# rechaza el envío completo y el prospecto no recibe NADA.
WA_MAX_TEXTO = 4000

# Palabras EXACTAS con las que un prospecto se da de baja de las campañas.
# Al detectarlas, el contacto se marca opt_out y ninguna campaña vuelve a
# tocarlo — puede seguir chateando normal, solo queda fuera de los masivos.
_OPT_OUT_PALABRAS = {"baja", "stop", "alto", "cancelar", "no molestar",
                     "darme de baja", "no me escribas", "unsubscribe"}

# TOPE DURO de contactos por campaña. Meta limita cuántas conversaciones de
# marketing puede abrir un número según su nivel (250 / 1,000 / 10,000...);
# pasarse hace que Meta rechace envíos y hasta baje la calidad del número.
# Se puede subir sin tocar código con WA2_CAMPANA_TOPE en Railway.
WA2_CAMPANA_TOPE = settings.wa2_campaign_limit

# Cajón de Supabase donde viven las fotos, audios y documentos de WhatsApp.
WA_MEDIA_BUCKET = settings.wa2_media_bucket

# Transcripción de notas de voz (mismo Groq/Whisper que ya usa el resto).
GROQ_API_KEY = settings.groq_api_key
GROQ_BASE    = settings.groq_base

# Candado por conversación: dos mensajes del mismo prospecto jamás deben
# generar dos respuestas al mismo tiempo.
_LOCKS: dict = {}


def _lock_conv(conversacion_id: str) -> asyncio.Lock:
    lock = _LOCKS.get(conversacion_id)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[conversacion_id] = lock
        if len(_LOCKS) > 5000:  # no dejar que crezca para siempre
            for k in list(_LOCKS.keys())[:1000]:
                if not _LOCKS[k].locked():
                    _LOCKS.pop(k, None)
    return lock

# TOPE DURO de respuestas de IA por conversación.
# Cada mensaje entrante que contesta la IA es una llamada a Claude que paga
# Broquer, no el agente. El campo `max_mensajes_ia` del entrenamiento lo puede
# ajustar cada quien hacia ABAJO, pero nadie puede pasarse de este número ni
# dejarlo en ilimitado — ni siquiera dejando el campo en 0, que es como están
# hoy todas las filas viejas. Sin esto, un solo número con tráfico pesado
# (o un prospecto necio, o un bot ajeno escribiéndole) puede generar una
# cuenta abierta de API. Se puede subir sin tocar código con la variable
# WA2_TOPE_IA en Railway.
WA2_TOPE_IA = settings.wa2_ai_limit

router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])

from routers.whatsapp_training import TRAINING_DEFAULTS, _calificacion_para_prompt, _conocimiento_para_prompt, _en_horario, _reglas_para_prompt


from routers.whatsapp_time import construir_ics as _construir_ics, fecha_hora_utc_iso as _fecha_hora_utc_iso, fmt_fecha_larga as _fmt_fecha_larga, hora_local as _hora_local, now_iso as _now





from routers.whatsapp_policy import _conv_pausada, _ia_decide, _modo_conv, _parse_ts









async def _pausar_por_respuesta_manual(conv: dict, numero: dict, entren: dict | None = None) -> dict:
    """El agente respondió a mano (desde Broquer o desde el WhatsApp de su
    celular). Según la configuración del número, la IA se hace a un lado en
    ese chat: para siempre, o por un rato (pausa temporal). En cualquier caso
    se cierra la sesión de "cliente nuevo": el agente ya tomó el chat."""
    if entren is None:
        entren = await _entrenamiento_de(numero["user_id"], numero["id"])
    info = {"ia_pausada": False, "ia_pausada_hasta": None, "para_siempre": False}
    cambios: dict = {"ia_sesion_nueva": False}
    if entren.get("pausa_al_responder", True) and _modo_conv(conv) != "off":
        dur = 0
        try:
            dur = int(entren.get("pausa_duracion_min") or 0)
        except Exception:
            pass
        if dur <= 0:
            cambios.update({"ia_modo": "off", "ai_enabled": False, "ia_pausada_hasta": None})
            info.update({"ia_pausada": True, "para_siempre": True})
        else:
            hasta = (datetime.now(timezone.utc) + timedelta(minutes=dur)).isoformat()
            cambios["ia_pausada_hasta"] = hasta
            info.update({"ia_pausada": True, "ia_pausada_hasta": hasta})
    guardado = await sb_patch("wa2_conversaciones", {"id": f"eq.{conv['id']}"}, cambios)
    if not guardado and info["ia_pausada"]:
        # Migración pendiente (columnas nuevas ausentes): degradar al
        # comportamiento clásico para que JAMÁS contesten dos en un chat.
        await sb_patch("wa2_conversaciones", {"id": f"eq.{conv['id']}"}, {"ai_enabled": False})
    conv.update({k: v for k, v in cambios.items()})
    return info




from routers.whatsapp_utils import in_filter as _in_filter, money as _money, normaliza_mx as _normaliza_mx, parsear_presupuesto as _parsear_presupuesto







# =============================================================================
# Helpers de Supabase — compatibilidad sobre Core
# =============================================================================
from routers.whatsapp_data import sb_delete, sb_get, sb_patch, sb_post









from routers.whatsapp_access import _ids_visibles, _require_user







# =============================================================================
# 1) CONEXIÓN DE NÚMEROS (Embedded Signup) — igual flujo de Meta, tabla propia
# =============================================================================
class ConnectReq(BaseModel):
    code: str
    waba_id: str | None = None
    phone_number_id: str | None = None
    coexistence: bool = False
    alias: str | None = None


@router.post("/connect")
async def wa2_connect(req: ConnectReq, request: Request):
    user_id = await _require_user(request)
    if not META_APP_ID or not META_APP_SECRET:
        raise HTTPException(status_code=500, detail="META_APP_ID o META_APP_SECRET no configurados")

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{GRAPH_API}/oauth/access_token", params={
            "client_id": META_APP_ID, "client_secret": META_APP_SECRET, "code": req.code,
        })
        if r.status_code != 200:
            log.error("Meta token error %s: %s", r.status_code, r.text)
            raise HTTPException(status_code=400, detail="No se pudo obtener el token de Meta")
        tok = r.json()
        business_token = tok.get("access_token", "")
        expires_in = tok.get("expires_in")

    if not business_token:
        raise HTTPException(status_code=400, detail="Meta no devolvió un token de acceso")

    waba_id = (req.waba_id or "").strip()
    phone_number_id = (req.phone_number_id or "").strip()

    if not waba_id:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{GRAPH_API}/debug_token", params={
                "input_token": business_token, "access_token": f"{META_APP_ID}|{META_APP_SECRET}",
            })
            if r.status_code == 200:
                for s in r.json().get("data", {}).get("granular_scopes", []):
                    if s.get("scope") == "whatsapp_business_management":
                        ids = s.get("target_ids") or []
                        if ids:
                            waba_id = ids[0]
                            break
    if not waba_id:
        raise HTTPException(status_code=400, detail="No se pudo identificar la cuenta de WhatsApp Business")

    waba_name = "WhatsApp Business"
    phone_number = ""
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{GRAPH_API}/{waba_id}", params={"access_token": business_token, "fields": "name"})
        if r.status_code == 200:
            waba_name = r.json().get("name") or waba_name
        r = await c.get(f"{GRAPH_API}/{waba_id}/phone_numbers",
                        params={"access_token": business_token, "fields": "id,display_phone_number"})
        phones = r.json().get("data", []) if r.status_code == 200 else []

    if phone_number_id:
        match = next((p for p in phones if p.get("id") == phone_number_id), None)
        if match:
            phone_number = (match.get("display_phone_number") or "").replace("+", "").replace(" ", "")
    elif phones:
        phone_number_id = phones[0].get("id", "")
        phone_number = (phones[0].get("display_phone_number") or "").replace("+", "").replace(" ", "")

    if not phone_number_id:
        raise HTTPException(status_code=400, detail="No se encontró un número en tu cuenta de WhatsApp Business")

    payload = {
        "user_id": user_id,
        "phone_number_id": phone_number_id,
        "display_number": phone_number,
        "waba_id": waba_id,
        "waba_name": waba_name,
        "alias": (req.alias or waba_name or "Línea de WhatsApp").strip(),
        "access_token": business_token,
        "ia_enabled": True,
        # Reconectar es justamente el arreglo cuando el token murió: limpia la marca.
        "token_valido": True,
        "token_error_at": None,
        "updated_at": _now(),
    }
    if expires_in:
        try:
            payload["token_expires_at"] = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + int(expires_in), timezone.utc).isoformat()
        except Exception:
            pass

    existing = await sb_get("wa2_numeros", {"phone_number_id": f"eq.{phone_number_id}", "select": "id", "limit": "1"})
    if existing:
        await sb_patch("wa2_numeros", {"phone_number_id": f"eq.{phone_number_id}"}, payload)
        numero_id = existing[0]["id"]
    else:
        payload["created_at"] = _now()
        created = await sb_post("wa2_numeros", payload)
        numero_id = created[0]["id"] if created else None

    if not numero_id:
        # Antes esto seguía de largo y regresaba "ok":true aunque nada se hubiera
        # guardado (ej. la tabla wa2_numeros aún no estaba visible para la API justo
        # después de correr el SQL). Así el usuario creía tener el número conectado
        # cuando en realidad no había ninguna fila — los mensajes entrantes nunca
        # encontraban con quién hacer match y se perdían en silencio.
        raise HTTPException(status_code=500,
            detail="No se pudo guardar el número en la base de datos. Vuelve a intentar en un minuto "
                   "(si acabas de correr el SQL de este módulo, Supabase a veces tarda en reconocer las "
                   "tablas nuevas).")

    # Suscribe la app a ESTA waba con callback ALTERNO -> nunca toca /whatsapp/webhook.
    # Y LUEGO se verifica leyendo la propia suscripción: Meta puede aceptar la
    # llamada (200) sin que el override realmente haya quedado activo, así que no
    # basta con revisar el status code de la petición.
    override_confirmado = False
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{GRAPH_API}/{waba_id}/subscribed_apps",
                         params={"access_token": business_token},
                         json={"override_callback_uri": WA2_WEBHOOK_URL, "verify_token": WA2_VERIFY_TOKEN})
        if r.status_code >= 400:
            log.error("No se pudo suscribir override_callback_uri de %s: %s", waba_id, r.text)
        r2 = await c.get(f"{GRAPH_API}/{waba_id}/subscribed_apps", params={"access_token": business_token})
        if r2.status_code < 300:
            for app_sub in r2.json().get("data", []):
                if app_sub.get("override_callback_uri") == WA2_WEBHOOK_URL:
                    override_confirmado = True
                    break
        else:
            log.error("No se pudo verificar subscribed_apps de %s: %s", waba_id, r2.text)

    await sb_patch("wa2_numeros", {"id": f"eq.{numero_id}"}, {"webhook_verificado": override_confirmado})

    if req.coexistence:
        log.info("Coexistencia: se omite /register para %s (ya registrado)", phone_number_id)
    else:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{GRAPH_API}/{phone_number_id}/register",
                             params={"access_token": business_token},
                             json={"messaging_product": "whatsapp", "pin": WA2_REGISTER_PIN})
            if r.status_code >= 400:
                log.warning("Registro de %s: %s", phone_number_id, r.text)

    # Entrenamiento por default para el número nuevo, si aún no tiene uno propio
    tiene_entren = await sb_get("wa2_entrenamiento", {
        "user_id": f"eq.{user_id}", "numero_id": f"eq.{numero_id}", "select": "id", "limit": "1"})
    if not tiene_entren and numero_id:
        base = await sb_get("wa2_entrenamiento", {
            "user_id": f"eq.{user_id}", "numero_id": "is.null", "select": "*", "limit": "1"})
        fila = dict(base[0]) if base else dict(TRAINING_DEFAULTS)
        fila.pop("id", None); fila.pop("created_at", None); fila.pop("updated_at", None)
        fila["numero_id"] = numero_id
        fila["user_id"] = user_id
        await sb_post("wa2_entrenamiento", fila)

    log.info("WhatsApp2 conectado: user=%s waba=%s phone=%s verificado=%s",
             user_id, waba_id, phone_number, override_confirmado)
    resultado = {"ok": True, "numero_id": numero_id, "phone_number": phone_number,
                "waba_name": waba_name, "alias": payload["alias"], "webhook_verificado": override_confirmado}
    if not override_confirmado:
        resultado["advertencia"] = (
            "El número se guardó, pero Meta no confirmó que vaya a mandar los mensajes a "
            "WhatsApp 2.0. Puede que sigan llegando al WhatsApp original. Usa el botón "
            "'Verificar conexión' en unos minutos; si sigue en rojo, dímelo.")
    return resultado


@router.get("/numeros/{numero_id}/verificar")
async def wa2_numero_verificar(numero_id: str, request: Request):
    """Vuelve a preguntarle a Meta, EN VIVO, si este número de verdad está mandando
    sus mensajes al webhook de WhatsApp 2.0. No confía en lo que se guardó al conectar:
    ese estado pudo cambiar después (ej. alguien reconectó el mismo número en el
    WhatsApp original, lo que le quita el override a este)."""
    user_id = await _require_user(request)
    rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": f"eq.{user_id}",
                                        "select": "waba_id,access_token", "limit": "1"})
    if not rows or not rows[0].get("waba_id") or not rows[0].get("access_token"):
        raise HTTPException(status_code=404, detail="Número no encontrado")
    waba_id, token = rows[0]["waba_id"], rows[0]["access_token"]
    verificado = False
    callback_actual = None
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{GRAPH_API}/{waba_id}/subscribed_apps", params={"access_token": token})
        if r.status_code < 300:
            for app_sub in r.json().get("data", []):
                callback_actual = app_sub.get("override_callback_uri")
                if callback_actual == WA2_WEBHOOK_URL:
                    verificado = True
                    break
        else:
            raise HTTPException(status_code=502, detail=f"Meta respondió con error: {r.text[:200]}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo consultar a Meta: {e}")

    await sb_patch("wa2_numeros", {"id": f"eq.{numero_id}"}, {"webhook_verificado": verificado})
    return {"webhook_verificado": verificado, "callback_actual": callback_actual}


@router.get("/numeros")
async def wa2_numeros_list(request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_numeros", {
        "user_id": _in_filter(ids), "select": "*", "order": "created_at.asc"})
    for r in rows:
        r.pop("access_token", None)
        r["es_mio"] = r.get("user_id") == user_id
    return {"numeros": rows}


class NumeroPatchReq(BaseModel):
    alias: str | None = None
    ia_enabled: bool | None = None
    numero_personal: str | None = None


@router.patch("/numeros/{numero_id}")
async def wa2_numero_patch(numero_id: str, req: NumeroPatchReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    body = {"updated_at": _now()}
    if req.alias is not None:
        body["alias"] = req.alias.strip()
    if req.ia_enabled is not None:
        body["ia_enabled"] = req.ia_enabled
    if req.numero_personal is not None:
        # El número PERSONAL del asesor: desde ahí le escribe a su propio número
        # de Broquer y lo atiende Broq (modo asesor), no la recepcionista.
        # Cadena vacía = quitarlo. Se guarda normalizado (solo dígitos, 52 fijo).
        body["numero_personal"] = _normaliza_mx(req.numero_personal) or None
    await sb_patch("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids)}, body)
    return {"ok": True}


@router.delete("/numeros/{numero_id}")
async def wa2_numero_delete(numero_id: str, request: Request):
    """Elimina un número de WhatsApp Y todo lo que dependía de él.

    Antes esto solo borraba la fila de wa2_numeros: las conversaciones, los
    mensajes y los contactos del número quedaban huérfanos y la bandeja los
    seguía mostrando. Ahora se borra en cascada — chats, mensajes, archivos
    del almacenamiento, contactos de WhatsApp, agenda, entrenamiento propio
    del número, campañas y automatizaciones. Los Contactos del CRM NO se
    tocan: esos los decide el agente desde el módulo de Contactos."""
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids),
                                        "select": "waba_id,access_token", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    if rows[0].get("waba_id") and rows[0].get("access_token"):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                await c.delete(f"{GRAPH_API}/{rows[0]['waba_id']}/subscribed_apps",
                               params={"access_token": rows[0]["access_token"]})
        except Exception:
            pass

    # 1) Conversaciones del número (en páginas, por si son muchas)
    conv_ids: list[str] = []
    pagina = 0
    while pagina < 20:
        lote = await sb_get("wa2_conversaciones", {"numero_id": f"eq.{numero_id}",
                                                   "select": "id", "limit": "1000",
                                                   "offset": str(pagina * 1000)})
        conv_ids.extend(c["id"] for c in lote if c.get("id"))
        if len(lote) < 1000:
            break
        pagina += 1

    # 2) Archivos de esos mensajes: se borran del almacenamiento ANTES de
    #    borrar las filas, porque después ya no habría forma de saber sus rutas.
    for i in range(0, len(conv_ids), 50):
        grupo = conv_ids[i:i + 50]
        archivos, pag = [], 0
        while pag < 40:
            lote = await sb_get("wa2_mensajes", {"conversacion_id": _in_filter(grupo),
                                                 "media_path": "not.is.null",
                                                 "select": "media_path", "limit": "1000",
                                                 "offset": str(pag * 1000)})
            archivos.extend(m.get("media_path") for m in lote)
            if len(lote) < 1000:
                break
            pag += 1
        await _borrar_archivos(archivos)
        await sb_delete("wa2_mensajes", {"conversacion_id": _in_filter(grupo)})

    # 3) El resto de las tablas del número, y al final el número mismo
    if conv_ids:
        for grupo in [conv_ids[i:i + 60] for i in range(0, len(conv_ids), 60)]:
            try:
                await sb_delete("wa2_flujo_estados", {"conversacion_id": _in_filter(grupo)})
            except Exception:
                pass
    await sb_delete("wa2_conversaciones", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_contactos", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_agenda", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_entrenamiento", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_campanas", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_automatizaciones", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids)})
    log.info("Número %s eliminado con todo lo suyo (%s conversaciones) por %s",
             numero_id, len(conv_ids), user_id)
    return {"ok": True}


# =============================================================================
# 2) ENTRENAMIENTO (identidad de la IA, por número o plantilla default)
# =============================================================================
from routers.whatsapp_training_api import router as whatsapp_training_api_router
router.include_router(whatsapp_training_api_router)







class ProbarReq(BaseModel):
    numero_id: str | None = None
    historial: list = []          # [{"rol":"prospecto"|"ia","texto":"..."}]
    mensaje: str


@router.post("/probar")
async def wa2_probar(req: ProbarReq, request: Request):
    """Banco de pruebas: platica con la IA EXACTAMENTE como lo haría un
    prospecto, con el entrenamiento y el catálogo reales, pero sin mandar un
    solo WhatsApp a nadie, sin crear contactos y sin tocar la base.

    Hasta ahora la única forma de saber si el entrenamiento quedó bien era
    esperar a que llegara un prospecto de verdad y rezar. Eso es justo lo que
    no puede pasar el día del lanzamiento con AMPI."""
    user_id = await _require_user(request)

    numero_id = req.numero_id or ""
    if numero_id:
        ids = await _ids_visibles(user_id)
        n = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids),
                                         "select": "id,user_id", "limit": "1"})
        if not n:
            raise HTTPException(status_code=404, detail="Número no encontrado")
        dueño = n[0]["user_id"]
    else:
        dueño = user_id

    entren = await _entrenamiento_de(dueño, numero_id)
    agente = await _perfil_agente(dueño)

    history = []
    for h in (req.historial or [])[-HISTORY_LIMIT:]:
        texto = (h.get("texto") or "").strip()
        if not texto:
            continue
        history.append({"role": "assistant" if h.get("rol") == "ia" else "user", "content": texto})
    history.append({"role": "user", "content": req.mensaje})

    contexto = (f"Atiendes prospectos de {agente['nombre']}, asesor inmobiliario"
                f"{(' en ' + agente['zona']) if agente['zona'] else ''}. "
                "Si no sabes por qué propiedad escribe, pregúntale qué busca.")

    resultado = await recepcion2_responde(history, contexto, agente, entren)

    # Si la IA quiso mandar propiedades, se hace la MISMA búsqueda real contra
    # el catálogo, para que se vea si de verdad encuentra lo que debería.
    propiedades, aviso = [], None
    accion = resultado.get("accion")
    if isinstance(accion, dict) and accion.get("tipo") == "enviar_inmuebles":
        filtros = accion.get("filtros") or {}
        if not filtros.get("precio_max"):
            respaldo = _parsear_presupuesto(resultado.get("presupuesto") or "")
            if respaldo:
                filtros = {**filtros, "precio_max": respaldo}
        props, sin_resultados = await _buscar_inmuebles(dueño, filtros)
        propiedades = [{"id": p.get("id"), "titulo": p.get("titulo") or p.get("tipo"),
                        "resumen": _texto_inmueble(p).replace("\n", " · ")} for p in props[:3]]
        if sin_resultados:
            aviso = ("La IA buscó en tu catálogo y no encontró nada en esa zona. "
                     "Al prospecto real le avisaría con honestidad, sin ofrecerle otra ubicación.")
        filtros_usados = filtros
    else:
        filtros_usados = None

    return {
        "reply": resultado.get("reply"),
        "temperatura": resultado.get("temperatura"),
        "score": resultado.get("score"),
        "presupuesto": resultado.get("presupuesto"),
        "forma_pago": resultado.get("forma_pago"),
        "busca": resultado.get("busca"),
        "resumen": resultado.get("resumen"),
        "accion": accion,
        "filtros": filtros_usados,
        "propiedades": propiedades,
        "aviso": aviso,
        "falla_tecnica": bool(resultado.get("_falla_tecnica")),
    }


async def _alta_inmueble(user_id: str, datos: dict, wa_id: str, fotos: list | None = None) -> str | None:
    """Da de alta un inmueble que un tercero le mandó al asesor por WhatsApp.

    Nace SIEMPRE con estatus 'no_activa': no aparece en el sitio público del
    asesor, no se le ofrece a ningún comprador y no se sincroniza a ningún
    lado. Es un borrador que espera revisión humana. Un dato que llegó por
    WhatsApp de alguien que no conocemos no puede tratarse como inventario
    real: ni el precio, ni la titularidad, ni siquiera que la casa exista
    están verificados.
    """
    tipo = (datos.get("tipo") or "").strip() or "Propiedad"
    colonia = (datos.get("colonia") or "").strip()
    operacion = (datos.get("operacion") or "").strip().lower()
    if operacion not in ("venta", "renta"):
        operacion = "venta"

    titulo = (datos.get("titulo") or "").strip() or \
        " ".join(x for x in [tipo, "en", operacion, ("· " + colonia) if colonia else ""] if x).strip()

    try:
        precio = float(datos.get("precio")) if datos.get("precio") not in (None, "") else None
    except Exception:
        precio = None

    def _entero(v):
        try:
            return int(float(v))
        except Exception:
            return None

    # org_id explícito: estas filas nacen con la service key, así que la base
    # NO puede deducir la empresa por la sesión (no hay sesión). Sin esto, el
    # inmueble queda huérfano de empresa y el dueño no puede ni borrarlo.
    ctx_org = await get_org_context(user_id)
    org_id = (ctx_org or {}).get("org_id")

    fila = {
        "user_id": user_id,
        "org_id": org_id,
        "titulo": titulo[:200],
        "tipo": tipo,
        "operacion": operacion,
        "precio": precio,
        "moneda": (datos.get("moneda") or "MXN").upper()[:4],
        "colonia": colonia or None,
        "ciudad": (datos.get("ciudad") or "").strip() or None,
        "calle": (datos.get("calle") or "").strip() or None,
        "recamaras": _entero(datos.get("recamaras")),
        "banos": _entero(datos.get("banos")),
        "estacionamientos": _entero(datos.get("estacionamientos")),
        "m2_construccion": _entero(datos.get("m2_construccion")),
        "m2_terreno": _entero(datos.get("m2_terreno")),
        "descripcion": (datos.get("descripcion") or "").strip() or None,
        "fotos": [f for f in (fotos or []) if f][:20],
        "estatus": "no_activa",
        "descripcion_privada": (
            f"Alta automática desde WhatsApp ({_normaliza_mx(wa_id)}) el "
            f"{_hora_local().strftime('%d/%m/%Y %H:%M')}. "
            "Datos proporcionados por un tercero, SIN VERIFICAR. "
            "Revisa precio, ubicación, medidas y titularidad antes de activarla."),
        "created_at": _now(),
        "updated_at": _now(),
    }
    creada = await sb_post("propiedades", fila)
    if not creada:
        log.error("No se pudo dar de alta el inmueble de WhatsApp (user=%s)", user_id)
        return None
    return creada[0].get("id")


async def _entrenamiento_de(user_id: str, numero_id: str) -> dict:
    rows = await sb_get("wa2_entrenamiento", {
        "user_id": f"eq.{user_id}", "numero_id": f"eq.{numero_id}", "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    rows = await sb_get("wa2_entrenamiento", {
        "user_id": f"eq.{user_id}", "numero_id": "is.null", "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    return dict(TRAINING_DEFAULTS)






# =============================================================================
# 3) EL CEREBRO — Anthropic, con JSON estructurado + acciones
# =============================================================================
from routers.whatsapp_brain import _recepcion2_responde_core


async def recepcion2_responde(history: list, contexto: str, agente: dict, entren: dict) -> dict:
    return await _recepcion2_responde_core(
        history,
        contexto,
        agente,
        entren,
        TRAINING_DEFAULTS=TRAINING_DEFAULTS,
        _fmt_fecha_larga=_fmt_fecha_larga,
        _hora_local=_hora_local,
        _calificacion_para_prompt=_calificacion_para_prompt,
        _reglas_para_prompt=_reglas_para_prompt,
        _conocimiento_para_prompt=_conocimiento_para_prompt,
        httpx=httpx,
        asyncio=asyncio,
        json=json,
        ANTHROPIC_BASE=ANTHROPIC_BASE,
        ANTHROPIC_API_KEY=ANTHROPIC_API_KEY,
        WA2_MODEL=WA2_MODEL,
        log=log,
    )



# =============================================================================
# 4) BÚSQUEDA Y ENVÍO DE INMUEBLES (catálogo real del usuario)
# =============================================================================
from routers.whatsapp_property_search import _buscar_inmuebles





from routers.whatsapp_property_view import _fotos_a_imagenes, _propiedad_para_ficha, _texto_inmueble







async def _generar_ficha_pdf(p_ficha: dict) -> tuple[str | None, str | None]:
    """Llama al MISMO generador de PDF (Playwright) que usa el módulo de
    Ficha técnica — no se reescribe nada, solo se usa por HTTP. Devuelve
    (url_publica, filename) o (None, None) si no se pudo generar a tiempo."""
    try:
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.post(f"{BROQUER_API_BASE}/ficha-pdf", json=p_ficha)
        if r.status_code >= 400:
            log.warning("No se pudo generar la ficha PDF: %s %s", r.status_code, r.text[:200])
            return None, None
        d = r.json()
        token = d.get("token")
        if not token:
            return None, None
        return f"{BROQUER_API_BASE}/ficha-pdf/{token}", d.get("filename") or "ficha.pdf"
    except Exception as e:
        log.warning("Timeout/error generando ficha PDF: %s", e)
        return None, None


async def _wa_send_document_link(numero: dict, wa_id: str, url: str, filename: str, caption: str = "") -> str | None:
    """Manda un documento por URL pública directa (sin subirlo primero) —
    válido porque /ficha-pdf/{token} ya es una URL pública servida por Broquer."""
    if not numero.get("access_token"):
        return None
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json={"messaging_product": "whatsapp", "to": wa_id, "type": "document",
                               "document": {"link": url, "filename": filename, "caption": caption[:1024]}})
        if r.status_code >= 400:
            log.error("Envío de ficha PDF falló (%s): %s", numero["phone_number_id"], r.text[:300])
            return None
        d = r.json()
        msgs = d.get("messages") or []
        return msgs[0].get("id") if msgs else None


# =============================================================================
# 5) CITAS / AGENDA (calendario del usuario dentro de Broquer)
# =============================================================================




class AgendarReq(BaseModel):
    conversacion_id: str | None = None
    inmueble_id: str | None = None
    titulo: str
    fecha: str
    hora: str
    notas: str | None = None


@router.post("/agendar")
async def wa2_agendar(req: AgendarReq, request: Request):
    """Agenda una visita: crea la tarea en el módulo de Tareas (ahí se
    concentran todas, no solo las de WhatsApp) y, si la cita viene de una
    conversación con un prospecto real, le manda la invitación .ics."""
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)

    dueño_id = user_id
    contacto = None
    numero = None
    if req.conversacion_id:
        conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{req.conversacion_id}", "user_id": _in_filter(ids),
                                                        "select": "*", "limit": "1"})
        if not conv_rows:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        conv = conv_rows[0]
        dueño_id = conv["user_id"]
        contacto_rows = await sb_get("wa2_contactos", {"id": f"eq.{conv['contacto_id']}", "select": "*", "limit": "1"})
        contacto = contacto_rows[0] if contacto_rows else None
        numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{conv['numero_id']}", "select": "*", "limit": "1"})
        numero = numero_rows[0] if numero_rows else None
        await sb_patch("wa2_contactos", {"id": f"eq.{conv['contacto_id']}"}, {"etapa": "Cita"})

    titulo = req.titulo.strip() or "Visita"
    if contacto and contacto.get("nombre") and contacto["nombre"] not in titulo:
        titulo = f"{titulo} — {contacto['nombre']} (WhatsApp)"
    elif req.conversacion_id:
        titulo = f"{titulo} (WhatsApp)"

    entren_zona = await _entrenamiento_de(dueño_id, (numero or {}).get("id", ""))
    tarea = {
        "user_id": dueño_id,
        "titulo": titulo,
        "fecha_entrega": _fecha_hora_utc_iso(req.fecha, req.hora, entren_zona.get("zona_horaria")),
        "notas": req.notas or None,
        "propiedad_id": req.inmueble_id or None,
        "contacto_id": (contacto or {}).get("contacto_crm_id"),
    }
    creada = await sb_post("tareas", tarea)
    if not creada:
        raise HTTPException(status_code=500, detail="No se pudo crear la tarea. Intenta de nuevo.")
    tarea_id = creada[0]["id"]

    # Además de la columna suelta, se deja el vínculo en las tablas de
    # varios-a-varios: así la tarea aparece también desde la pestaña de
    # Tareas del Contacto/Inmueble aunque después se le agreguen más vínculos.
    crm_id = (contacto or {}).get("contacto_crm_id")
    if crm_id:
        await sb_post("tareas_contactos", {"user_id": dueño_id, "tarea_id": tarea_id, "contacto_id": crm_id})
    if req.inmueble_id:
        await sb_post("tareas_propiedades", {"user_id": dueño_id, "tarea_id": tarea_id, "propiedad_id": req.inmueble_id})

    if contacto and numero:
        ics = _construir_ics(req.fecha, req.hora, titulo, req.notas or "", entren_zona.get("zona_horaria"))
        await _wa_send_document(numero, contacto.get("wa_id"), ics.encode("utf-8"),
                               "cita.ics", "Toca el archivo para agregarla a tu calendario.")

    return {"ok": True, "tarea": creada[0]}


# =============================================================================
# 6) ENVÍO POR WHATSAPP (Cloud API)
# =============================================================================
async def _revisar_token(numero: dict, err: dict | None) -> None:
    """Si Meta responde que el token ya no sirve, deja constancia y avisa.

    El token de un número puede morir sin que nadie haga nada malo: el agente
    revocó el permiso desde su Facebook, sacó a Broquer de su Business, o Meta
    lo caducó. Cuando eso pasa NO hay forma de renovarlo solos — el token de
    integración de negocio se emite una sola vez, en el Embedded Signup. El
    único arreglo real es que el agente vuelva a apretar 'Conectar número'.

    Así que lo que se puede hacer, y es lo que hace esto, es enterarse a la
    primera y decírselo, en vez de dejar que los mensajes se pierdan en
    silencio durante días. También apaga la IA de ese número: no tiene caso
    quemar llamadas a Claude generando respuestas que nunca van a salir.
    """
    if not err or err.get("code") not in (190, 102):
        return
    numero_id = numero.get("id")
    if not numero_id:
        return
    try:
        if numero.get("token_valido") is False:
            return  # ya estaba marcado, no repitas el aviso en cada mensaje
        await sb_patch("wa2_numeros", {"id": f"eq.{numero_id}"},
                      {"token_valido": False, "token_error_at": _now(), "ia_enabled": False})
        numero["token_valido"] = False
        await enviar_push(numero.get("user_id"), "Tu WhatsApp se desconectó",
                          "Meta dejó de aceptar la conexión de tu número. Entra a WhatsApp en "
                          "Broquer y vuelve a apretar 'Conectar número' para reactivarlo.",
                          datos={"tipo": "whatsapp"})
        log.error("Token inválido para el número %s (user %s): %s",
                  numero.get("phone_number_id"), numero.get("user_id"), err.get("message"))
    except Exception as e:  # pragma: no cover — avisar nunca debe tumbar el envío
        log.warning("No se pudo marcar el token inválido de %s: %s", numero_id, e)


async def _wa_send_text_detallado(numero: dict, wa_id: str, texto: str) -> tuple[str | None, dict | None]:
    """Como _wa_send_text, pero además regresa el error real de Meta (código y
    mensaje) cuando falla — necesario para distinguir 'ventana de 24h cerrada'
    (código 131047) de cualquier otro problema, en vez de tragarse el error."""
    if not numero.get("access_token"):
        return None, {"code": None, "message": "Este número no tiene un token de acceso válido."}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json={"messaging_product": "whatsapp", "to": wa_id,
                               "type": "text", "text": {"body": texto, "preview_url": False}})
        if r.status_code >= 400:
            log.error("Envío de texto falló (%s): %s", numero["phone_number_id"], r.text[:300])
            try:
                err = (r.json().get("error") or {})
            except Exception:
                err = {}
            detalle = {"code": err.get("code"), "message": err.get("message") or "No se pudo enviar el mensaje."}
            await _revisar_token(numero, detalle)
            return None, detalle
        d = r.json()
        msgs = d.get("messages") or []
        return (msgs[0].get("id") if msgs else None), None


async def _wa_send_text(numero: dict, wa_id: str, texto: str) -> str | None:
    """Manda texto. Si se pasa del tope de WhatsApp lo parte en varios mensajes:
    antes, un texto de más de 4096 caracteres hacía que Meta rechazara el envío
    COMPLETO y el prospecto no recibiera absolutamente nada."""
    texto = (texto or "").strip()
    if not texto:
        return None
    if len(texto) <= WA_MAX_TEXTO:
        wamid, _ = await _wa_send_text_detallado(numero, wa_id, texto)
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
        ultimo, _ = await _wa_send_text_detallado(numero, wa_id, parte)
    return ultimo


async def _wa_marcar_leido(numero: dict, wamid: str | None, escribiendo: bool = True) -> None:
    """Pone la palomita azul y muestra 'escribiendo…' del lado del prospecto.

    Sin esto la conversación se siente falsa por los dos lados: el prospecto ve
    que sus mensajes nunca se marcan como leídos y luego, de golpe, aparece una
    respuesta larguísima escrita en cero segundos. Con esto se lee igual que un
    humano contestando desde su celular. Nunca debe tumbar nada si falla."""
    if not wamid or not numero.get("access_token"):
        return
    cuerpo = {"messaging_product": "whatsapp", "status": "read", "message_id": wamid}
    if escribiendo:
        cuerpo["typing_indicator"] = {"type": "text"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json=cuerpo)
    except Exception as e:
        log.debug("No se pudo marcar como leído: %s", e)


async def _descargar_media(numero: dict, media_id: str) -> tuple[bytes | None, str]:
    """Baja un archivo que mandó el prospecto (nota de voz, foto, documento).
    Meta lo entrega en dos pasos: primero la URL temporal, luego el binario —
    y ambos requieren el token del número. Devuelve (bytes, mime)."""
    if not media_id or not numero.get("access_token"):
        return None, ""
    headers = {"Authorization": f"Bearer {numero['access_token']}"}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(f"{GRAPH_API}/{media_id}", headers=headers)
            if r.status_code >= 400:
                log.warning("No se pudo obtener la media %s: %s", media_id, r.text[:200])
                return None, ""
            info = r.json()
            url, mime = info.get("url"), info.get("mime_type") or ""
            if not url:
                return None, ""
            rb = await c.get(url, headers=headers)
            if rb.status_code >= 400 or not rb.content:
                return None, ""
            return rb.content, mime
    except Exception as e:
        log.warning("Error bajando media %s: %s", media_id, e)
        return None, ""



async def _transcribir_audio(contenido: bytes, mime: str) -> str:
    """Convierte una nota de voz en texto con Whisper (el mismo Groq que ya usa
    Broquer). Esto NO es un lujo: en México el prospecto manda audios todo el
    tiempo, y hasta ahora la IA solo veía la palabra '[audio]' y contestaba a
    ciegas —o peor, contestaba cualquier cosa— sin haber oído nada."""
    if not GROQ_API_KEY or not contenido:
        return ""
    ext = "ogg"
    if "mp4" in mime or "m4a" in mime:
        ext = "m4a"
    elif "mpeg" in mime or "mp3" in mime:
        ext = "mp3"
    elif "wav" in mime:
        ext = "wav"
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{GROQ_BASE}/audio/transcriptions",
                             headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                             data={"model": "whisper-large-v3", "language": "es",
                                   "response_format": "json"},
                             files={"file": (f"nota.{ext}", contenido, mime or "audio/ogg")})
        if r.status_code >= 400:
            log.warning("Whisper falló: %s %s", r.status_code, r.text[:200])
            return ""
        return (r.json().get("text") or "").strip()
    except Exception as e:
        log.warning("Error transcribiendo audio: %s", e)
        return ""


async def _describir_imagen(contenido: bytes, mime: str) -> str:
    """Le pide a Claude que lea la foto que mandó el prospecto (una captura de
    un anuncio, la fachada de la casa que quiere vender, un comprobante…).
    Antes la IA recibía literalmente '[image]' y le respondía de adivinanza."""
    if not ANTHROPIC_API_KEY or not contenido or len(contenido) > 4_500_000:
        return ""
    import base64
    if mime not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        mime = "image/jpeg"
    try:
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post(f"{ANTHROPIC_BASE}/messages",
                             headers={"x-api-key": ANTHROPIC_API_KEY,
                                      "anthropic-version": "2023-06-01",
                                      "Content-Type": "application/json"},
                             json={"model": WA2_MODEL, "max_tokens": 300, "messages": [{
                                 "role": "user", "content": [
                                     {"type": "image", "source": {"type": "base64",
                                      "media_type": mime,
                                      "data": base64.b64encode(contenido).decode()}},
                                     {"type": "text", "text":
                                      "Describe en dos o tres frases, en español, qué se ve en esta "
                                      "imagen que un prospecto le mandó por WhatsApp a un asesor "
                                      "inmobiliario. Si hay texto legible (precios, direcciones, datos), "
                                      "transcríbelo. Solo la descripción, sin preámbulo."}]}]})
        if r.status_code >= 400:
            return ""
        data = r.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    except Exception as e:
        log.warning("No se pudo describir la imagen: %s", e)
        return ""


async def _wa_send_image(numero: dict, wa_id: str, url: str, caption: str = "") -> str | None:
    if not numero.get("access_token"):
        return None
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json={"messaging_product": "whatsapp", "to": wa_id,
                               "type": "image", "image": {"link": url, "caption": caption[:1024]}})
        if r.status_code >= 400:
            log.error("Envío de imagen falló (%s): %s", numero["phone_number_id"], r.text[:300])
            return None
        d = r.json()
        msgs = d.get("messages") or []
        return msgs[0].get("id") if msgs else None


async def _wa_send_document(numero: dict, wa_id: str, contenido: bytes, filename: str, caption: str) -> None:
    """Sube el .ics como media y lo manda como documento adjunto."""
    if not numero.get("access_token"):
        return
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            up = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/media",
                              headers={"Authorization": f"Bearer {numero['access_token']}"},
                              data={"messaging_product": "whatsapp", "type": "text/calendar"},
                              files={"file": (filename, contenido, "text/calendar")})
            media_id = up.json().get("id") if up.status_code < 300 else None
            if not media_id:
                return
            await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                        headers={"Authorization": f"Bearer {numero['access_token']}"},
                        json={"messaging_product": "whatsapp", "to": wa_id, "type": "document",
                              "document": {"id": media_id, "filename": filename, "caption": caption}})
    except Exception as e:
        log.warning("No se pudo mandar el .ics: %s", e)


# =============================================================================
# 6.5) PLANTILLAS — únicas que WhatsApp permite mandar fuera de la ventana de
# 24h desde el último mensaje del prospecto. Se crean aquí, Meta las aprueba
# (minutos a días) y luego se pueden usar para reabrir la conversación.
# =============================================================================
class PlantillaCrearReq(BaseModel):
    numero_id: str
    nombre: str
    idioma: str = "es_MX"
    categoria: str = "UTILITY"  # UTILITY | MARKETING | AUTHENTICATION
    cuerpo: str
    variables_ejemplo: list[str] = []
    footer: str | None = None


@router.get("/plantillas")
async def wa2_plantillas_list(request: Request, numero_id: str):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids),
                                                "select": "*", "limit": "1"})
    if not numero_rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    numero = numero_rows[0]
    if not numero.get("waba_id") or not numero.get("access_token"):
        return {"plantillas": []}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{GRAPH_API}/{numero['waba_id']}/message_templates",
                        params={"access_token": numero["access_token"], "limit": 100})
    if r.status_code >= 400:
        log.error("No se pudieron listar plantillas (%s): %s", numero["waba_id"], r.text[:300])
        raise HTTPException(status_code=502, detail="Meta no pudo listar las plantillas de este número.")
    plantillas = []
    for t in r.json().get("data", []):
        cuerpo = next((c.get("text") for c in t.get("components", []) if c.get("type") == "BODY"), "")
        plantillas.append({
            "nombre": t.get("name"), "idioma": t.get("language"), "estatus": t.get("status"),
            "categoria": t.get("category"), "cuerpo": cuerpo,
        })
    return {"plantillas": plantillas}


@router.post("/plantillas")
async def wa2_plantilla_crear(req: PlantillaCrearReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{req.numero_id}", "user_id": _in_filter(ids),
                                                "select": "*", "limit": "1"})
    if not numero_rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    numero = numero_rows[0]
    if not numero.get("waba_id") or not numero.get("access_token"):
        raise HTTPException(status_code=400, detail="Este número todavía no está conectado del todo con Meta.")

    nombre = re.sub(r"[^a-z0-9_]", "_", req.nombre.strip().lower())
    componentes = [{"type": "BODY", "text": req.cuerpo}]
    if req.variables_ejemplo:
        componentes[0]["example"] = {"body_text": [req.variables_ejemplo]}
    if req.footer:
        componentes.append({"type": "FOOTER", "text": req.footer})

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{GRAPH_API}/{numero['waba_id']}/message_templates",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json={"name": nombre, "language": req.idioma,
                               "category": req.categoria, "components": componentes})
    if r.status_code >= 400:
        log.error("No se pudo crear la plantilla (%s): %s", numero["waba_id"], r.text[:300])
        try:
            err = r.json().get("error", {})
            msg = err.get("error_user_msg") or err.get("message")
        except Exception:
            msg = None
        raise HTTPException(status_code=502,
            detail=msg or "Meta rechazó la plantilla. Revisa que el texto no tenga datos personales sueltos "
                          "(usa {{1}}, {{2}}… para lo que cambie en cada envío) y que no repita mucho espacio o salto de línea.")
    return {"ok": True, "nombre": nombre}


class PlantillaEnviarReq(BaseModel):
    conversacion_id: str
    nombre: str
    idioma: str
    variables: list[str] = []


@router.post("/mensajes/plantilla")
async def wa2_enviar_plantilla(req: PlantillaEnviarReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{req.conversacion_id}", "user_id": _in_filter(ids),
                                                    "select": "*", "limit": "1"})
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv = conv_rows[0]
    contacto_rows = await sb_get("wa2_contactos", {"id": f"eq.{conv['contacto_id']}", "select": "*", "limit": "1"})
    contacto = contacto_rows[0] if contacto_rows else {}
    numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{conv['numero_id']}", "select": "*", "limit": "1"})
    if not numero_rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    numero = numero_rows[0]

    componentes = []
    if req.variables:
        componentes.append({"type": "body", "parameters": [{"type": "text", "text": v} for v in req.variables]})

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json={"messaging_product": "whatsapp", "to": contacto.get("wa_id"), "type": "template",
                               "template": {"name": req.nombre, "language": {"code": req.idioma},
                                           "components": componentes}})
    if r.status_code >= 400:
        log.error("Envío de plantilla falló (%s): %s", numero["phone_number_id"], r.text[:300])
        try:
            msg = r.json().get("error", {}).get("message")
        except Exception:
            msg = None
        raise HTTPException(status_code=502, detail=msg or "Meta no pudo mandar la plantilla. Revisa que esté aprobada.")

    d = r.json()
    msgs = d.get("messages") or []
    wamid = msgs[0].get("id") if msgs else None
    resumen = f"[Plantilla: {req.nombre}]" + (" " + " · ".join(req.variables) if req.variables else "")
    await _guardar_mensaje(conv["user_id"], conv["contacto_id"], conv["id"], wamid, "out", "agente", resumen)
    return {"ok": True}


# =============================================================================
# 7) PERFIL DEL AGENTE (nombre público y zona, para que la IA se presente bien)
# =============================================================================
from routers.whatsapp_agent_profile import _perfil_agente



# =============================================================================
# 8) WEBHOOK — recibe TODOS los números conectados a este módulo
# =============================================================================
@router.get("/webhook")
def wa2_verify_webhook(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == WA2_VERIFY_TOKEN:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    return Response(content="forbidden", status_code=403)


@router.post("/webhook")
async def wa2_receive_webhook(request: Request, background: BackgroundTasks):
    raw = await request.body()

    # Sin secreto NO se procesa nada. Antes esto dejaba pasar todo cuando la
    # variable faltaba: cualquiera en internet podía inyectar mensajes falsos,
    # hacer que la IA contestara sola y quemar la cuenta de Anthropic.
    # Ahora se cierra la puerta y se grita en el log.
    if not WA2_APP_SECRET:
        log.error("WA_APP_SECRET y META_APP_SECRET vacíos: el webhook de WhatsApp "
                  "queda CERRADO hasta que se configure uno de los dos en Railway.")
        return Response(status_code=503)

    sig = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(WA2_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        log.warning("Firma de webhook 2.0 inválida")
        return Response(status_code=403)

    try:
        payload = json.loads(raw)
    except Exception:
        return Response(status_code=200)

    try:
        ok, trabajo = await _persistir_entrantes(payload)
    except Exception as e:
        log.exception("persistir_entrantes (2.0) reventó, pido reintento a Meta: %s", e)
        return Response(status_code=503)
    if not ok:
        return Response(status_code=503)

    for item in trabajo:
        background.add_task(_procesar_en_segundo_plano, item)

    return Response(status_code=200)


async def _get_numero(phone_number_id: str) -> dict | None:
    rows = await sb_get("wa2_numeros", {"phone_number_id": f"eq.{phone_number_id}", "select": "*", "limit": "1"})
    return rows[0] if rows else None


from routers.whatsapp_crm_sync import _crear_contacto_crm_core, _sincronizar_contacto_crm_core

async def _crear_contacto_crm(user_id: str, wa_id: str, nombre: str | None) -> str | None:
    return await _crear_contacto_crm_core(
        user_id,
        wa_id,
        nombre,
        datetime=datetime,
        timezone=timezone,
        _normaliza_mx=_normaliza_mx,
        get_org_context=get_org_context,
        _now=_now,
        sb_post=sb_post,
        log=log,
    )



async def _sincronizar_contacto_crm(user_id: str, contacto_wa2: dict, resultado_ia: dict | None = None) -> None:
    return await _sincronizar_contacto_crm_core(
        user_id,
        contacto_wa2,
        resultado_ia,
        _now=_now,
        sb_get=sb_get,
        _hora_local=_hora_local,
        sb_patch=sb_patch,
        log=log,
    )



from routers.whatsapp_agenda import _agenda_upsert_core, _es_asesor_core, _solo_digitos_core

def _solo_digitos(t: str) -> str:
    return _solo_digitos_core(t, re=re)



def _es_asesor(numero: dict, wa_id: str) -> bool:
    return _es_asesor_core(numero, wa_id, _normaliza_mx=_normaliza_mx)



async def _agenda_upsert(user_id: str, numero_id: str, telefono: str,
                         nombre: str | None = None, conocido: bool | None = None) -> None:
    return await _agenda_upsert_core(
        user_id,
        numero_id,
        telefono,
        nombre,
        conocido,
        sb_get=sb_get,
        _now=_now,
        sb_patch=sb_patch,
        sb_post=sb_post,
        log=log,
    )



from routers.whatsapp_conversation_state import _get_o_crea_contacto_core, _get_o_crea_conversacion_core

async def _get_o_crea_contacto(user_id: str, numero_id: str, wa_id: str, nombre: str | None,
                               crear_crm: bool = True) -> dict:
    return await _get_o_crea_contacto_core(
        user_id,
        numero_id,
        wa_id,
        nombre,
        crear_crm,
        sb_get=sb_get,
        _solo_digitos=_solo_digitos,
        _crear_contacto_crm=_crear_contacto_crm,
        sb_post=sb_post,
        _now=_now,
    )



async def _get_o_crea_conversacion(user_id: str, numero_id: str, contacto_id: str,
                                   ia_default: bool = True) -> dict:
    return await _get_o_crea_conversacion_core(
        user_id,
        numero_id,
        contacto_id,
        ia_default,
        sb_get=sb_get,
        _now=_now,
        sb_post=sb_post,
    )



from routers.whatsapp_message_state import _guardar_mensaje_core, _resolver_inmueble_id_core

async def _guardar_mensaje(user_id: str, contacto_id: str, conversacion_id: str, wamid: str | None,
                          direction: str, sender: str, body: str, media_url: str | None = None,
                          media_path: str | None = None) -> None:
    return await _guardar_mensaje_core(
        user_id, contacto_id, conversacion_id, wamid, direction, sender, body, media_url, media_path,
        _now=_now, sb_post=sb_post, sb_get=sb_get, log=log, sb_patch=sb_patch,
    )



def _resolver_inmueble_id(inmueble_txt: str, ultimas: list) -> str | None:
    return _resolver_inmueble_id_core(inmueble_txt, ultimas)



async def _persistir_entrantes(payload: dict):
    trabajo = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            val = change.get("value", {})
            phone_number_id = (val.get("metadata") or {}).get("phone_number_id")
            if not phone_number_id:
                continue
            numero = await _get_numero(phone_number_id)
            if not numero:
                log.warning("Número no registrado en wa2_numeros: %s — ignorado", phone_number_id)
                continue
            contactos_meta = {c["wa_id"]: c.get("profile", {}).get("name") for c in val.get("contacts", [])}

            # ── COEXISTENCIA: ecos de lo que el asesor manda DESDE SU CELULAR ──
            # Cuando el número coexiste con la app de WhatsApp Business, lo que
            # el asesor contesta desde su teléfono llega aquí como message_echoes
            # (campo smb_message_echoes). Sin esto Broquer nunca se enteraba de
            # que el asesor ya respondió y la IA le contestaba ENCIMA al mismo
            # prospecto. El eco se guarda en la bandeja como mensaje del agente
            # y apaga la IA de esa conversación, igual que el envío manual.
            entren_eco = None  # se carga una sola vez si hay ecos que pausar
            for eco in (val.get("message_echoes") or []):
                wa_dest = _solo_digitos(eco.get("to") or "")
                if not wa_dest:
                    continue
                ya = await sb_get("wa2_mensajes", {"wa_message_id": f"eq.{eco.get('id')}",
                                                   "select": "id", "limit": "1"})
                if ya:
                    continue
                if eco.get("type") == "text":
                    cuerpo = (eco.get("text") or {}).get("body", "")
                else:
                    cuerpo = f"[{eco.get('type') or 'mensaje'} enviado por el asesor desde su celular]"
                # Eco hacia el NÚMERO PERSONAL del asesor: es él mismo
                # tecleando desde su celular de negocio dentro de su chat con
                # Broq. Se guarda para que la conversación quede completa, pero
                # NO es un comando (los comandos son los que MANDA desde su
                # número personal y llegan como entrantes) — Broq no responde
                # a esto ni se dispara la lógica de pausa/conocidos.
                if _es_asesor(numero, wa_dest):
                    contacto_self = await _get_o_crea_contacto(numero["user_id"], numero["id"],
                                                               wa_dest, "Tú · Broq", crear_crm=False)
                    if not contacto_self:
                        continue
                    conv_self = await _get_o_crea_conversacion(numero["user_id"], numero["id"],
                                                               contacto_self["id"], ia_default=False)
                    await _guardar_mensaje(numero["user_id"], contacto_self["id"], conv_self["id"],
                                          eco.get("id"), "out", "agente", cuerpo)
                    continue

                contacto_eco = await _get_o_crea_contacto(numero["user_id"], numero["id"], wa_dest, None)
                if not contacto_eco:
                    continue
                conv_eco = await _get_o_crea_conversacion(numero["user_id"], numero["id"],
                                                          contacto_eco["id"], ia_default=False)
                await _guardar_mensaje(numero["user_id"], contacto_eco["id"], conv_eco["id"],
                                      eco.get("id"), "out", "agente", cuerpo)
                # El asesor contestó desde su celular: la IA se hace a un
                # lado según la config del número (pausa temporal o para
                # siempre), exactamente igual que al escribir desde Broquer.
                if entren_eco is None:
                    entren_eco = await _entrenamiento_de(numero["user_id"], numero["id"])
                await _pausar_por_respuesta_manual(conv_eco, numero, entren_eco)
                if not contacto_eco.get("conocido"):
                    await sb_patch("wa2_contactos", {"id": f"eq.{contacto_eco['id']}"},
                                   {"conocido": True, "updated_at": _now()})
                    await _agenda_upsert(numero["user_id"], numero["id"], wa_dest, conocido=True)

            # ── COEXISTENCIA: agenda del celular del asesor ────────────────────
            # Meta sincroniza los contactos del teléfono (smb_app_state_sync).
            # Ese nombre — el que el asesor le puso a la persona en SU agenda —
            # es la fuente correcta para nombrar leads en Broquer; el nombre que
            # el lead se puso a sí mismo en WhatsApp es el último recurso.
            for sync in (val.get("state_sync") or []):
                if sync.get("type") != "contact":
                    continue
                cont_s = sync.get("contact") or {}
                tel_s = _solo_digitos(cont_s.get("phone_number") or "")
                nombre_s = (cont_s.get("full_name") or cont_s.get("first_name") or "").strip()
                if not tel_s or (sync.get("action") or "add") == "remove":
                    continue
                await _agenda_upsert(numero["user_id"], numero["id"], tel_s, nombre=nombre_s or None)
                filas_c = await sb_get("wa2_contactos", {"numero_id": f"eq.{numero['id']}",
                                                         "wa_id": f"eq.{tel_s}",
                                                         "select": "*", "limit": "1"})
                if filas_c and nombre_s:
                    c0 = filas_c[0]
                    cambios_c = {"nombre_agenda": nombre_s, "updated_at": _now()}
                    # El nombre de agenda solo manda si el lead no se ha
                    # presentado él mismo en el chat (esa es la prioridad 1).
                    if not (c0.get("nombre_chat") or "").strip():
                        cambios_c["nombre"] = nombre_s
                    await sb_patch("wa2_contactos", {"id": f"eq.{c0['id']}"}, cambios_c)

            # ── COEXISTENCIA: historial de chats previos a la conexión ─────────
            # En el onboarding Meta manda los chats que el número ya tenía
            # (campo history). No se importan esos mensajes: solo sirve para
            # marcar a esas personas como CONOCIDAS del asesor, para que la
            # recepcionista jamás les caiga en frío como a un prospecto nuevo.
            for bloque_h in (val.get("history") or []):
                for hilo in (bloque_h.get("threads") or []):
                    tel_h = _solo_digitos(str(hilo.get("id") or ""))
                    if tel_h:
                        await _agenda_upsert(numero["user_id"], numero["id"], tel_h, conocido=True)

            for msg in val.get("messages", []):
                wa_id = msg.get("from")
                if not wa_id:
                    continue

                # SEGURIDAD: nunca proceses ni respondas mensajes de ANTES de
                # que el número se conectara a Broquer. Meta puede reenviar
                # eventos de mensajes viejos (coexistencia con un número que
                # ya tenía historial, reintentos de webhook, etc.) y sin este
                # filtro la IA le contestaría a un mensaje de hace semanas
                # como si fuera de ahorita — sin que el agente lo autorizara.
                try:
                    msg_ts = int(msg.get("timestamp") or 0)
                    creado_en = numero.get("created_at")
                    if msg_ts and creado_en:
                        creado_dt = datetime.fromisoformat(creado_en.replace("Z", "+00:00"))
                        if datetime.fromtimestamp(msg_ts, timezone.utc) < creado_dt:
                            log.warning("Mensaje anterior a la conexión del número %s — ignorado (%s)",
                                       numero.get("phone_number_id"), msg.get("id"))
                            continue
                except Exception:
                    pass

                # La revisión de duplicados va ANTES de tocar la media: Meta
                # reenvía el mismo webhook cuando no le contestamos rápido, y
                # transcribir dos veces la misma nota de voz se paga dos veces.
                existe = await sb_get("wa2_mensajes", {"wa_message_id": f"eq.{msg.get('id')}",
                                                       "select": "id", "limit": "1"})
                if existe:
                    continue

                tipo_msg = msg.get("type")
                texto = ""
                media_bytes: bytes | None = None
                media_mime = ""
                media_sufijo = "archivo"
                if tipo_msg == "text":
                    texto = (msg.get("text") or {}).get("body", "")
                elif tipo_msg in ("audio", "voice"):
                    # Nota de voz: se oye de verdad. Antes se guardaba "[audio]"
                    # y la IA le contestaba al prospecto sin tener idea de lo
                    # que le dijo — la peor tontería posible frente a un cliente.
                    media_id = (msg.get(tipo_msg) or {}).get("id")
                    media_bytes, media_mime = await _descargar_media(numero, media_id)
                    media_sufijo = "nota-de-voz"
                    dicho = await _transcribir_audio(media_bytes, media_mime) if media_bytes else ""
                    texto = f"[nota de voz] {dicho}" if dicho else \
                        "[nota de voz que no se pudo transcribir]"
                elif tipo_msg == "image":
                    media_id = (msg.get("image") or {}).get("id")
                    pie = (msg.get("image") or {}).get("caption") or ""
                    media_bytes, media_mime = await _descargar_media(numero, media_id)
                    media_sufijo = "foto"
                    visto = await _describir_imagen(media_bytes, media_mime) if media_bytes else ""
                    texto = "[foto] " + " ".join(x for x in [pie, visto] if x).strip()
                    if not visto and not pie:
                        texto = "[foto que no se pudo leer]"
                elif tipo_msg == "location":
                    loc = msg.get("location") or {}
                    partes_loc = [loc.get("name"), loc.get("address"),
                                  f"{loc.get('latitude')},{loc.get('longitude')}"]
                    texto = "[ubicación] " + " · ".join(str(x) for x in partes_loc if x)
                elif tipo_msg == "document":
                    doc = msg.get("document") or {}
                    media_bytes, media_mime = await _descargar_media(numero, doc.get("id"))
                    media_sufijo = re.sub(r"[^A-Za-z0-9._-]", "_", (doc.get("filename") or "documento"))[:60]
                    texto = f"[documento] {doc.get('filename') or ''} {doc.get('caption') or ''}".strip()
                elif tipo_msg == "video":
                    vid = msg.get("video") or {}
                    media_bytes, media_mime = await _descargar_media(numero, vid.get("id"))
                    media_sufijo = "video"
                    texto = f"[video] {vid.get('caption') or ''}".strip()
                elif tipo_msg == "contacts":
                    texto = "[el prospecto compartió una tarjeta de contacto]"
                elif tipo_msg in ("button", "interactive"):
                    inter = msg.get("interactive") or {}
                    texto = ((msg.get("button") or {}).get("text")
                             or (inter.get("button_reply") or {}).get("title")
                             or (inter.get("list_reply") or {}).get("title")
                             or "[respuesta a un botón]")
                else:
                    texto = f"[mensaje de tipo {tipo_msg or 'desconocido'}]"

                es_asesor = _es_asesor(numero, wa_id)
                if es_asesor:
                    # Escribe el DUEÑO desde su número personal registrado: es
                    # una orden para Broq (modo asesor), nunca un prospecto.
                    contacto = await _get_o_crea_contacto(numero["user_id"], numero["id"], wa_id,
                                                          "Tú · Broq", crear_crm=False)
                    conv = await _get_o_crea_conversacion(numero["user_id"], numero["id"],
                                                          contacto["id"], ia_default=False)
                else:
                    contacto = await _get_o_crea_contacto(numero["user_id"], numero["id"], wa_id,
                                                          contactos_meta.get(wa_id))
                    conv = await _get_o_crea_conversacion(numero["user_id"], numero["id"], contacto["id"],
                                                         ia_default=not contacto.get("conocido"))

                media_url, media_path = (None, None)
                if media_bytes:
                    media_url, media_path = await _guardar_archivo(
                        numero["user_id"], conv["id"], media_bytes, media_mime, media_sufijo)

                await _guardar_mensaje(numero["user_id"], contacto["id"], conv["id"], msg.get("id"),
                                      "in", "agente" if es_asesor else "lead", texto, media_url, media_path)
                if not es_asesor:
                    await sb_patch("wa2_conversaciones", {"id": f"eq.{conv['id']}"},
                                  {"unread_count": (conv.get("unread_count") or 0) + 1})

                # ── BAJA de campañas por palabra clave (opt-out) ──────────
                # Si el mensaje ES exactamente una palabra de baja, el
                # contacto queda fuera de todas las campañas para siempre.
                # Nunca truena el webhook: si la columna no existe todavía
                # (migración pendiente), simplemente no pasa nada.
                if (not es_asesor and tipo_msg == "text"
                        and texto.strip().lower().rstrip(".!") in _OPT_OUT_PALABRAS):
                    try:
                        await sb_patch("wa2_contactos", {"id": f"eq.{contacto['id']}"},
                                       {"opt_out": True, "updated_at": _now()})
                    except Exception:
                        pass

                trabajo.append({"numero": numero, "contacto_id": contacto["id"],
                               "conversacion_id": conv["id"], "wa_id": wa_id, "texto": texto,
                               "wa_message_id": msg.get("id"), "es_asesor": es_asesor,
                               # Cuándo había escrito ANTES de este mensaje (ya con el
                               # mensaje guardado, last_inbound_at apunta a ahorita y no
                               # serviría para saber si es un cliente nuevo).
                               "prev_inbound_at": conv.get("last_inbound_at")})

            # ── Acuses de Meta (enviado / entregado / leído / FALLIDO) ──────
            # Esto se ignoraba por completo. Lo grave no es perderse la
            # palomita: es que cuando Meta RECHAZA un mensaje (número dado de
            # baja, plantilla no aprobada, ventana cerrada, límite de la
            # cuenta) el agente creía que su mensaje salió y nunca salió.
            for st in val.get("statuses", []):
                estado = st.get("status")
                if estado != "failed":
                    continue
                errs = st.get("errors") or [{}]
                err0 = errs[0] if errs else {}
                log.error("Mensaje NO entregado (%s): %s %s",
                          numero.get("phone_number_id"), err0.get("code"), err0.get("title"))
                await _revisar_token(numero, {"code": err0.get("code"),
                                              "message": err0.get("title") or ""})
                try:
                    await sb_patch("wa2_mensajes", {"wa_message_id": f"eq.{st.get('id')}"},
                                   {"entrega_error": (err0.get("title") or "No se pudo entregar")[:200]})
                except Exception:
                    pass
                await enviar_push(numero.get("user_id"), "Un mensaje no se pudo entregar",
                                  err0.get("title") or "WhatsApp rechazó el envío. Revisa la conversación.",
                                  datos={"tipo": "whatsapp"})
    return True, trabajo


async def _procesar_en_segundo_plano(item: dict):
    numero = item["numero"]
    user_id = numero["user_id"]

    # OJO: aquí YA NO se manda la palomita azul. Antes se mandaba en cuanto
    # entraba el mensaje, aunque la IA estuviera apagada o el chat lo tuviera
    # que atender el agente: el prospecto veía "leído" sin que nadie lo hubiera
    # leído, y del lado de Broquer todo aparecía como atendido. Ahora la
    # palomita se manda solo cuando la IA de verdad va a contestar (más abajo,
    # en _responder_conversacion) o cuando el agente abre el chat en Broquer.

    # El aviso al celular del agente va ANTES de agrupar: aunque esta tarea se
    # retire por ráfaga, el agente tiene que enterarse de TODOS los mensajes.
    if not item.get("es_asesor"):  # avisarle al asesor de su propio mensaje no tiene caso
        contacto_push = await sb_get("wa2_contactos", {"id": f"eq.{item['contacto_id']}",
                                                       "select": "nombre", "limit": "1"})
        await enviar_push(user_id,
                          (contacto_push[0].get("nombre") if contacto_push else None) or "Nuevo mensaje de WhatsApp",
                          item["texto"], datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})

    # ── FLUJO EN CURSO ───────────────────────────────────────────────────
    # Si esta conversación tiene un flujo esperando respuesta (una pregunta
    # o un menú de opciones), este mensaje ES esa respuesta: la consume el
    # flujo, no la IA. Es la garantía de que un flujo jamás se corta a medias.
    if not item.get("es_asesor"):
        try:
            estado = await _flujo_estado_de(item["conversacion_id"])
            if estado and await _flujo_continuar(estado, item, numero, user_id):
                return
        except Exception as e:
            log.warning("Flujo activo falló (se sigue normal): %s", e)

    # ── FLUJOS / AUTOMATIZACIONES (recetas) ──────────────────────────────
    # Corren ANTES de agrupar ráfagas y antes de la IA: si el mensaje dispara
    # un flujo que responde, pregunta o pasa el chat (a ti o a la IA), ese
    # flujo manda y la IA ya no dice nada encima. Si el flujo solo pone
    # etiquetas, el camino normal (IA incluida) sigue igual.
    if not item.get("es_asesor"):
        try:
            if await _correr_automatizaciones(item, numero, user_id):
                return
        except Exception as e:
            log.warning("Automatizaciones fallaron (se sigue normal): %s", e)

    # ── AGRUPAR RÁFAGAS ──────────────────────────────────────────────────
    # La gente escribe en WhatsApp a pedacitos. Se espera unos segundos y, si
    # mientras tanto entró otro mensaje del prospecto, ESTA tarea se retira:
    # la que atienda el último mensaje contestará una sola vez y ya con todo
    # el contexto. Sin esto salían tres respuestas encimadas, se contradecían
    # entre sí y se pagaban tres llamadas a la IA por una sola pregunta.
    if WA2_DEBOUNCE:
        await asyncio.sleep(WA2_DEBOUNCE)
        ultimos = await sb_get("wa2_mensajes", {
            "conversacion_id": f"eq.{item['conversacion_id']}", "direction": "eq.in",
            "select": "wa_message_id", "order": "created_at.desc", "limit": "1"})
        if ultimos and item.get("wa_message_id") and \
           ultimos[0].get("wa_message_id") != item["wa_message_id"]:
            log.info("Ráfaga: se descarta la respuesta al mensaje %s, ya llegó uno más nuevo",
                     item["wa_message_id"])
            return

    async with _lock_conv(item["conversacion_id"]):
        if item.get("es_asesor"):
            await _broq_asesor(item, numero, user_id)
        else:
            await _responder_conversacion(item, numero, user_id)


# ══════════════════════════════════════════════════════════════════════════
# MODO ASESOR — el dueño del número le escribe a su propio número de Broquer
# DESDE SU NÚMERO PERSONAL registrado (texto o nota de voz, que ya llega
# transcrita) y Broq lo atiende: comentarios en contactos o tareas, pendientes
# nuevos y consultas del CRM. Jamás se activa para un lead: solo cuando el
# remitente es el número personal registrado del dueño (o el propio número).
# ══════════════════════════════════════════════════════════════════════════
ASESOR_TOOLS = [
    {"name": "buscar_contactos",
     "description": "Busca en el CRM del asesor por nombre, teléfono, email o notas. Úsala SIEMPRE antes de agregar un comentario a un contacto, para obtener su id exacto.",
     "input_schema": {"type": "object",
                      "properties": {"query": {"type": "string"}},
                      "required": ["query"]}},
    {"name": "buscar_tareas",
     "description": "Busca en las tareas/citas del asesor por título o notas. Úsala SIEMPRE antes de agregar un comentario a una tarea, para obtener su id exacto.",
     "input_schema": {"type": "object",
                      "properties": {"query": {"type": "string"}},
                      "required": ["query"]}},
    {"name": "buscar_propiedades",
     "description": "Busca en la cartera de inmuebles del asesor por título, colonia, calle, ciudad o clave interna. Úsala SIEMPRE antes de agregar un comentario a una propiedad, para obtener su id exacto.",
     "input_schema": {"type": "object",
                      "properties": {"query": {"type": "string"}},
                      "required": ["query"]}},
    {"name": "agregar_comentario",
     "description": "Agrega un comentario con fecha a las notas de un contacto, una tarea o una propiedad, sin borrar lo que ya había. Usa el id exacto que devolvió buscar_contactos, buscar_tareas o buscar_propiedades.",
     "input_schema": {"type": "object",
                      "properties": {"destino": {"type": "string", "enum": ["contacto", "tarea", "propiedad"]},
                                     "id": {"type": "string"},
                                     "comentario": {"type": "string"}},
                      "required": ["destino", "id", "comentario"]}},
    {"name": "crear_tarea",
     "description": "Crea una tarea o pendiente para el asesor, con fecha y hora opcionales, y opcionalmente vinculada a un contacto y/o un inmueble (usa sus ids exactos de las búsquedas).",
     "input_schema": {"type": "object",
                      "properties": {"titulo": {"type": "string"},
                                     "fecha": {"type": "string", "description": "YYYY-MM-DD, opcional"},
                                     "hora": {"type": "string", "description": "HH:MM en 24h, opcional"},
                                     "notas": {"type": "string"},
                                     "contacto_id": {"type": "string"},
                                     "propiedad_id": {"type": "string"}},
                      "required": ["titulo"]}},
]


from routers.whatsapp_advisor_context import _asesor_ctx_guardar_core

async def _asesor_ctx_guardar(conversacion_id: str, cambios: dict) -> None:
    return await _asesor_ctx_guardar_core(
        conversacion_id, cambios, sb_get=sb_get, sb_patch=sb_patch, log=log
    )



from routers.whatsapp_advisor_tools import _asesor_ejecutar_tool_core

async def _asesor_ejecutar_tool(user_id: str, name: str, args: dict, zona: str | None,
                                conversacion_id: str) -> str:
    return await _asesor_ejecutar_tool_core(
        user_id, name, args, zona, conversacion_id,
        sb_get=sb_get, _hora_local=_hora_local, _now=_now, sb_patch=sb_patch,
        _asesor_ctx_guardar=_asesor_ctx_guardar, _fecha_hora_utc_iso=_fecha_hora_utc_iso,
        sb_post=sb_post,
    )



from routers.whatsapp_advisor_brain import _broq_asesor_core

async def _broq_asesor(item: dict, numero: dict, user_id: str):
    return await _broq_asesor_core(
        item, numero, user_id,
        _entrenamiento_de=_entrenamiento_de, sb_get=sb_get, HISTORY_LIMIT=HISTORY_LIMIT,
        _fmt_fecha_larga=_fmt_fecha_larga, _hora_local=_hora_local, httpx=httpx,
        ANTHROPIC_BASE=ANTHROPIC_BASE, ANTHROPIC_API_KEY=ANTHROPIC_API_KEY, WA2_MODEL=WA2_MODEL,
        ASESOR_TOOLS=ASESOR_TOOLS, log=log, _asesor_ejecutar_tool=_asesor_ejecutar_tool,
        _wa_send_text=_wa_send_text, _guardar_mensaje=_guardar_mensaje,
    )



async def _responder_conversacion(item: dict, numero: dict, user_id: str):
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}", "select": "*", "limit": "1"})
    conv = conv_rows[0] if conv_rows else {}
    contacto_rows = await sb_get("wa2_contactos", {"id": f"eq.{item['contacto_id']}", "select": "*", "limit": "1"})
    contacto = contacto_rows[0] if contacto_rows else {}

    # (El aviso al celular ya se mandó en _procesar_en_segundo_plano.)

    entren = await _entrenamiento_de(user_id, numero["id"])
    if not entren.get("activo", True):
        return

    # ── Sesión de "cliente nuevo" (para el modo global "solo_nuevos") ──────
    # Cliente nuevo = número que nunca había escrito, o que llevaba más de
    # `nuevos_meses` sin escribir. La sesión se abre aquí y se cierra en
    # cuanto el agente responde a mano (el chat ya es suyo).
    if "prev_inbound_at" in item and not conv.get("ia_sesion_nueva"):
        prev_dt = _parse_ts(item.get("prev_inbound_at"))
        try:
            meses = int(entren.get("nuevos_meses") or 3)
        except Exception:
            meses = 3
        if prev_dt is None or (datetime.now(timezone.utc) - prev_dt).days >= meses * 30:
            conv["ia_sesion_nueva"] = True
            await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                           {"ia_sesion_nueva": True})

    if not _ia_decide(conv, entren, numero):
        return  # el humano tiene el control (modo del chat, pausa o modo global)
    if not _en_horario(entren):
        msg_fuera = entren.get("fuera_horario_msg") or "Gracias por tu mensaje, en cuanto abramos te contesto."
        await _wa_marcar_leido(numero, item.get("wa_message_id"))
        wamid = await _wa_send_text(numero, item["wa_id"], msg_fuera)
        await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid,
                              "out", "ia", msg_fuera)
        return

    palabras = entren.get("escalar_palabras") or []
    if isinstance(palabras, str):
        palabras = [p.strip() for p in palabras.split(",") if p.strip()]
    if any(p.lower() in item["texto"].lower() for p in palabras if p):
        await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                       {"ai_enabled": False, "ia_modo": "off"})
        await enviar_push(user_id, "Un prospecto pidió hablar contigo",
                          f"{contacto.get('nombre') or item['wa_id']}: {item['texto'][:100]}",
                          datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
        return

    # El tope del entrenamiento manda solo si es MÁS estricto que el tope duro.
    # Un 0 guardado (que antes significaba "ilimitado") ahora cae al tope duro.
    max_msj = entren.get("max_mensajes_ia") or 0
    if max_msj <= 0 or max_msj > WA2_TOPE_IA:
        max_msj = WA2_TOPE_IA
    conteo = await sb_get("wa2_mensajes", {"conversacion_id": f"eq.{item['conversacion_id']}",
                                           "sender": "eq.ia", "select": "id"})
    if len(conteo) >= max_msj:
        # Antes esto apagaba la IA y se salía en silencio: el prospecto se
        # quedaba escribiendo al vacío y el agente nunca se enteraba de que
        # ahora le tocaba a él. Ahora se le avisa.
        await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                       {"ai_enabled": False, "ia_modo": "off"})
        await enviar_push(user_id, "Un prospecto te está esperando",
                          f"{contacto.get('nombre') or item['wa_id']} lleva rato platicando con la IA. "
                          "Ya te toca a ti seguir la conversación.",
                          datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
        return

    # Ya se decidió que la IA sí va a contestar: hasta ahora se vale poner la
    # palomita azul y el "escribiendo…" del lado del prospecto.
    await _wa_marcar_leido(numero, item.get("wa_message_id"))

    historial_rows = await sb_get("wa2_mensajes", {
        "conversacion_id": f"eq.{item['conversacion_id']}", "select": "sender,body",
        "order": "created_at.desc", "limit": str(HISTORY_LIMIT)})
    historial_rows.reverse()
    history = [{"role": "assistant" if m["sender"] in ("ia", "agente") else "user", "content": m.get("body") or ""}
              for m in historial_rows]

    agente = await _perfil_agente(user_id)
    contexto = conv.get("property_ctx") or (
        f"Atiendes prospectos de {agente['nombre']}, asesor inmobiliario"
        f"{(' en ' + agente['zona']) if agente['zona'] else ''}. "
        "Si no sabes por qué propiedad escribe, pregúntale qué busca.")

    resultado = await recepcion2_responde(history, contexto, agente, entren)

    reply = resultado.get("reply") or "Gracias por tu mensaje."
    wamid = await _wa_send_text(numero, item["wa_id"], reply)
    await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid, "out", "ia", reply)

    if resultado.get("_falla_tecnica"):
        # La IA no pudo pensar la respuesta (la API venía caída o saturada).
        # Se le pasa la conversación al humano y se le avisa: un prospecto
        # esperando a un bot descompuesto es un prospecto perdido.
        await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                       {"ai_enabled": False, "ia_modo": "off"})
        await enviar_push(user_id, "La IA no pudo contestar",
                          f"{contacto.get('nombre') or item['wa_id']} está esperando respuesta. "
                          "Entra a la conversación tú.",
                          datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
        return

    # Actualiza la ficha del prospecto con lo que la IA acaba de calificar
    notas_actuales = contacto.get("notas") or []
    if resultado.get("nota"):
        notas_actuales = notas_actuales + [{"texto": resultado["nota"], "autor": "ia", "fecha": _now()}]
    # El nombre con el que el prospecto SE PRESENTÓ en el chat es la prioridad 1
    # (arriba de la agenda del celular y del nombre de WhatsApp).
    nombre_chat = (resultado.get("nombre") or "").strip() or (contacto.get("nombre_chat") or "").strip()
    update_contacto = {
        "temperatura": resultado.get("temperatura") or contacto.get("temperatura") or "Nuevo",
        "score": resultado.get("score") if resultado.get("score") is not None else contacto.get("score", 0),
        "presupuesto": resultado.get("presupuesto") or contacto.get("presupuesto"),
        "forma_pago": resultado.get("forma_pago") or contacto.get("forma_pago"),
        "busca": resultado.get("busca") or contacto.get("busca"),
        "resumen": resultado.get("resumen") or contacto.get("resumen"),
        "notas": notas_actuales,
        "updated_at": _now(),
    }
    if nombre_chat:
        update_contacto["nombre_chat"] = nombre_chat
        update_contacto["nombre"] = nombre_chat
    await sb_patch("wa2_contactos", {"id": f"eq.{item['contacto_id']}"}, update_contacto)
    await _sincronizar_contacto_crm(user_id, dict(contacto, **update_contacto), resultado)

    accion = resultado.get("accion")
    if isinstance(accion, dict):
        tipo = accion.get("tipo")
        if tipo == "enviar_inmuebles":
            filtros_ia = accion.get("filtros") or {}
            if not filtros_ia.get("precio_max"):
                # Respaldo: la IA no mandó precio_max en esta acción, pero si
                # el prospecto ya dio su presupuesto antes (queda en su ficha),
                # se usa de todos modos — no se le ofrece algo fuera de su rango
                # solo porque el mensaje más reciente no repitió el monto.
                respaldo = _parsear_presupuesto(resultado.get("presupuesto") or contacto.get("presupuesto") or "")
                if respaldo:
                    filtros_ia = {**filtros_ia, "precio_max": respaldo}
            props, zona_sin_resultados = await _buscar_inmuebles(user_id, filtros_ia)
            if props:
                enviados = []
                # Las fichas se arman EN PARALELO. En serie eran hasta 45
                # segundos por cada una: el prospecto leía "ahorita te las
                # comparto" y las recibía dos minutos y medio después, cuando
                # ya se había ido a otro anuncio.
                fichas = await asyncio.gather(
                    *[_generar_ficha_pdf(_propiedad_para_ficha(p)) for p in props[:3]],
                    return_exceptions=True)
                for idx, p in enumerate(props[:3]):
                    # Antes se mandaba foto+texto Y la ficha técnica (redundante,
                    # la ficha ya trae fotos y datos). Ahora solo la ficha.
                    resumen = _texto_inmueble(p).replace("\n", " · ")
                    ficha = fichas[idx] if idx < len(fichas) else None
                    url_pdf, filename = ficha if isinstance(ficha, tuple) else (None, None)
                    if url_pdf:
                        wamid = await _wa_send_document_link(
                            numero, item["wa_id"], url_pdf, filename or "ficha.pdf", resumen)
                        await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid,
                                              "out", "ia", f"[ficha técnica] {resumen}", url_pdf)
                    else:
                        # Si por lo que sea no se pudo armar el PDF a tiempo, que
                        # al menos le llegue la info en texto, no que no reciba nada.
                        wamid = await _wa_send_text(numero, item["wa_id"], _texto_inmueble(p))
                        await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid,
                                              "out", "ia", _texto_inmueble(p))
                    enviados.append({"id": p.get("id"), "titulo": p.get("titulo") or p.get("tipo") or "propiedad"})
                # Se recuerdan aquí (no en el historial de mensajes) para poder
                # adjuntar la propiedad correcta a la tarea si más adelante agenda una visita.
                await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                              {"ultimas_propiedades": enviados})
            elif zona_sin_resultados:
                # De verdad no hay nada en la zona que pidió: se le dice tal
                # cual, NUNCA se le manda una propiedad de otra ubicación
                # como si fuera lo que preguntó.
                zona_txt = (filtros_ia.get("colonia") or filtros_ia.get("zona_amplia")
                           or filtros_ia.get("ciudad") or "esa zona").strip()
                aviso = (f"Por ahora no tengo nada disponible en {zona_txt}. "
                         "Le aviso a mi asesor para que revise si tiene algo que no esté "
                         "publicado, o si prefieres te comparto opciones en otra zona cercana.")
                wamid2 = await _wa_send_text(numero, item["wa_id"], aviso)
                await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid2, "out", "ia", aviso)
                await enviar_push(user_id, "Un prospecto busca algo que no tienes publicado",
                                  f"{contacto.get('nombre') or item['wa_id']} pidió {zona_txt} y no hay inventario ahí.",
                                  datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
            else:
                aviso = "Por ahora no tengo una opción exacta, pero le aviso a mi asesor para que te comparta algo a la medida."
                wamid2 = await _wa_send_text(numero, item["wa_id"], aviso)
                await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid2, "out", "ia", aviso)

        elif tipo == "agendar_visita":
            fecha = accion.get("fecha"); hora = accion.get("hora")
            if fecha and hora:
                nombre_prospecto = contacto.get("nombre") or item["wa_id"]
                inmueble_txt = (accion.get("inmueble") or "").strip()
                titulo = f"Visita con {nombre_prospecto} (WhatsApp)"
                if inmueble_txt:
                    titulo += f" — {inmueble_txt}"
                crm_id = contacto.get("contacto_crm_id")
                propiedad_id = _resolver_inmueble_id(inmueble_txt, conv.get("ultimas_propiedades") or [])
                creada = await sb_post("tareas", {
                    "user_id": user_id, "titulo": titulo,
                    "fecha_entrega": _fecha_hora_utc_iso(fecha, hora, entren.get("zona_horaria")),
                    "notas": inmueble_txt or None,
                    "propiedad_id": propiedad_id,
                    "contacto_id": crm_id})
                if creada and crm_id:
                    await sb_post("tareas_contactos", {
                        "user_id": user_id, "tarea_id": creada[0]["id"], "contacto_id": crm_id})
                if creada and propiedad_id:
                    await sb_post("tareas_propiedades", {
                        "user_id": user_id, "tarea_id": creada[0]["id"], "propiedad_id": propiedad_id})
                await sb_patch("wa2_contactos", {"id": f"eq.{item['contacto_id']}"}, {"etapa": "Cita"})
                ics = _construir_ics(fecha, hora, titulo, inmueble_txt, entren.get("zona_horaria"))
                await _wa_send_document(numero, item["wa_id"], ics.encode("utf-8"),
                                       "cita.ics", "Toca el archivo para agregarla a tu calendario.")
                await enviar_push(user_id, "Nueva cita agendada",
                                  f"{nombre_prospecto} — {fecha} {hora} (revísala en Tareas)",
                                  datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})

        elif tipo == "registrar_inmueble":
            datos = accion.get("datos") or {}
            # Se recuperan las fotos que el remitente mandó EN ESTA conversación
            # para adjuntarlas al inmueble. Ya viven en el almacenamiento de
            # Broquer, así que son ligas propias y permanentes.
            fotos_rows = await sb_get("wa2_mensajes", {
                "conversacion_id": f"eq.{item['conversacion_id']}", "direction": "eq.in",
                "media_url": "not.is.null", "select": "body,media_url",
                "order": "created_at.desc", "limit": "20"})
            fotos = [f["media_url"] for f in fotos_rows
                     if (f.get("body") or "").lower().startswith("[foto")]
            fotos.reverse()

            inmueble_id = await _alta_inmueble(user_id, datos, item["wa_id"], fotos)
            if inmueble_id:
                # Quien mandó el inmueble queda vinculado como su Propietario en
                # el CRM (contactos_propiedades), para que al abrirlo en Mis
                # Inmuebles se sepa de inmediato de quién es y cómo contactarlo.
                crm_id_prop = contacto.get("contacto_crm_id")
                if crm_id_prop:
                    vinculo = await sb_post("contactos_propiedades", {
                        "user_id": user_id, "contacto_id": crm_id_prop,
                        "propiedad_id": inmueble_id, "relacion": "propietario"})
                    if not vinculo:
                        log.warning("No se pudo vincular al propietario %s con el inmueble %s",
                                    crm_id_prop, inmueble_id)
                # Al remitente NADA de promesas: un "gracias" y punto. Si se le
                # dijera "ya quedó registrada" creería que está publicada.
                gracias = "¡Muchas gracias!"
                wamid3 = await _wa_send_text(numero, item["wa_id"], gracias)
                await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"],
                                       wamid3, "out", "ia", gracias)
                await sb_patch("wa2_contactos", {"id": f"eq.{item['contacto_id']}"},
                               {"etapa": "Propietario"})
                etiqueta = " · ".join(x for x in [datos.get("tipo"), datos.get("colonia"),
                                                  _money(datos.get("precio"))] if x)
                await enviar_push(user_id, "Te mandaron un inmueble",
                                  f"{contacto.get('nombre') or item['wa_id']}: {etiqueta or 'un inmueble'}. "
                                  "Quedó guardado como No activo — revísalo en Mis Inmuebles.",
                                  datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
            else:
                await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                               {"ai_enabled": False, "ia_modo": "off"})
                await enviar_push(user_id, "No se pudo guardar un inmueble",
                                  f"{contacto.get('nombre') or item['wa_id']} te mandó una propiedad y "
                                  "no se pudo registrar. Entra a la conversación.",
                                  datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})

        elif tipo == "pasar_a_humano":
            await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                           {"ai_enabled": False, "ia_modo": "off"})
            await enviar_push(user_id, "Un prospecto necesita de ti",
                              accion.get("motivo") or "La IA te pasó esta conversación.",
                              datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})


# =============================================================================
# 9) BANDEJA — conversaciones, mensajes, notas, handoff manual, envío manual
# =============================================================================
@router.get("/conversaciones")
async def wa2_conversaciones_list(request: Request, numero_id: str | None = None):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    params = {"user_id": _in_filter(ids), "select": "*,wa2_contactos(*)",
              "order": "last_message_at.desc", "limit": "200"}
    if numero_id and numero_id != "todos":
        params["numero_id"] = f"eq.{numero_id}"
    rows = await sb_get("wa2_conversaciones", params)

    # Vista previa del último mensaje de cada chat (como WhatsApp). Se resuelve
    # con UNA sola consulta: se traen los mensajes recientes del usuario en
    # orden descendente y se toma el primero que aparece de cada conversación.
    if rows:
        try:
            recientes = await sb_get("wa2_mensajes", {
                "user_id": _in_filter(ids),
                "select": "conversacion_id,body,direction,sender,created_at",
                "order": "created_at.desc", "limit": "1000",
            })
            vistos: dict = {}
            for m in recientes:
                cid = m.get("conversacion_id")
                if cid and cid not in vistos:
                    vistos[cid] = m
            for c in rows:
                ult = vistos.get(c.get("id"))
                if ult:
                    c["preview_texto"] = (ult.get("body") or "")[:120]
                    c["preview_direction"] = ult.get("direction")
                    c["preview_sender"] = ult.get("sender")
        except Exception:
            log.warning("No se pudo calcular la vista previa de las conversaciones")

    return {"conversaciones": rows}


@router.get("/mensajes")
async def wa2_mensajes_list(request: Request, conversacion_id: str,
                            limit: int = 30, before: str | None = None, after: str | None = None):
    """Mensajes de una conversación, paginados como WhatsApp.

    · Sin parámetros: devuelve los ÚLTIMOS `limit` mensajes (los más recientes),
      ya ordenados del más viejo al más nuevo para pintarlos de corrido.
    · `before=<created_at>`: devuelve la página ANTERIOR (mensajes más viejos),
      que es lo que se pide al hacer scroll hacia arriba.
    · `after=<created_at>`: solo lo que llegó después de esa marca — se usa en el
      refresco automático para no volver a bajar toda la conversación.
    """
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    limit = max(1, min(int(limit or 30), 100))

    base = {"conversacion_id": f"eq.{conversacion_id}", "user_id": _in_filter(ids), "select": "*"}

    if after:
        rows = await sb_get("wa2_mensajes", {**base, "created_at": f"gt.{after}",
                                             "order": "created_at.asc", "limit": "200"})
        return {"mensajes": rows, "hay_mas_antiguos": False, "incremental": True}

    params = {**base, "order": "created_at.desc", "limit": str(limit + 1)}
    if before:
        params["created_at"] = f"lt.{before}"
    rows = await sb_get("wa2_mensajes", params)

    hay_mas = len(rows) > limit
    if hay_mas:
        rows = rows[:limit]
    rows.reverse()

    # Bajar los mensajes ya NO marca la conversación como leída. Leer es un
    # acto del agente, no un efecto secundario de que el navegador refresque:
    # de eso se encarga POST /conversaciones/{id}/lectura.
    return {"mensajes": rows, "hay_mas_antiguos": hay_mas, "incremental": False}


class EnviarManualReq(BaseModel):
    conversacion_id: str
    texto: str


@router.post("/mensajes")
async def wa2_enviar_manual(req: EnviarManualReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{req.conversacion_id}", "user_id": _in_filter(ids),
                                                    "select": "*", "limit": "1"})
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv = conv_rows[0]
    contacto_rows = await sb_get("wa2_contactos", {"id": f"eq.{conv['contacto_id']}", "select": "*", "limit": "1"})
    contacto = contacto_rows[0] if contacto_rows else {}
    numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{conv['numero_id']}", "select": "*", "limit": "1"})
    if not numero_rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    numero = numero_rows[0]

    texto = (req.texto or "").strip()
    if not texto:
        raise HTTPException(status_code=400, detail="El mensaje viene vacío.")
    if len(texto) > WA_MAX_TEXTO:
        raise HTTPException(status_code=400,
            detail=f"El mensaje es demasiado largo ({len(texto)} caracteres). "
                   f"WhatsApp solo permite {WA_MAX_TEXTO}. Mándalo en dos partes.")

    wamid, error = await _wa_send_text_detallado(numero, contacto.get("wa_id"), texto)
    if error:
        if error.get("code") == 131047:
            raise HTTPException(status_code=409, detail={
                "ventana_cerrada": True,
                "mensaje": "Pasaron más de 24 horas desde el último mensaje del prospecto. "
                           "WhatsApp ya no deja mandar texto libre — usa una plantilla para reabrir la conversación.",
            })
        raise HTTPException(status_code=502, detail=error.get("message") or "No se pudo enviar el mensaje.")
    await _guardar_mensaje(conv["user_id"], conv["contacto_id"], conv["id"], wamid, "out", "agente", texto)

    # En cuanto el asesor escribe con sus propias manos, la IA se hace a un
    # lado en ESA conversación (para siempre o por el rato que él configuró
    # en Recepción IA). Si no, pasa lo más ridículo que puede pasar: el
    # prospecto contesta y le responden dos "personas" distintas, con
    # criterios distintos, en el mismo chat. Se reactiva con el control de IA.
    pausa = await _pausar_por_respuesta_manual(conv, numero)
    return {"ok": True, "ia_pausada": pausa["ia_pausada"],
            "ia_pausada_hasta": pausa["ia_pausada_hasta"],
            "para_siempre": pausa["para_siempre"]}


class LecturaReq(BaseModel):
    no_leida: bool = False


@router.post("/conversaciones/{conversacion_id}/lectura")
async def wa2_lectura(conversacion_id: str, req: LecturaReq, request: Request):
    """Marca la conversación como leída o como NO leída, a mano.

    · no_leida=False → se pone en cero el contador y, ahora sí, se le manda la
      palomita azul al prospecto: alguien de verdad abrió su mensaje.
    · no_leida=True  → el agente la deja pendiente aunque ya la haya abierto,
      igual que en WhatsApp. La palomita azul que ya se mandó no se puede
      quitar (Meta no lo permite), pero en Broquer la conversación vuelve a
      aparecer sin leer.
    """
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{conversacion_id}", "user_id": _in_filter(ids),
                                                    "select": "*", "limit": "1"})
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv = conv_rows[0]

    if req.no_leida:
        await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"},
                       {"no_leida": True, "unread_count": max(1, int(conv.get("unread_count") or 0))})
        return {"ok": True, "no_leida": True}

    await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"},
                   {"no_leida": False, "unread_count": 0})

    # Palomita azul al prospecto, sin "escribiendo…": lo leyó un humano, no la IA.
    wamid = conv.get("last_inbound_wamid")
    if wamid:
        numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{conv.get('numero_id')}",
                                                   "select": "*", "limit": "1"})
        if numero_rows:
            await _wa_marcar_leido(numero_rows[0], wamid, escribiendo=False)

    return {"ok": True, "no_leida": False}


class ConvPatchReq(BaseModel):
    ai_enabled: bool | None = None
    ia_modo: str | None = None      # 'auto' | 'on' | 'off'
    etapa: str | None = None


@router.patch("/conversaciones/{conversacion_id}")
async def wa2_conversacion_patch(conversacion_id: str, req: ConvPatchReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{conversacion_id}", "user_id": _in_filter(ids),
                                                    "select": "contacto_id", "limit": "1"})
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    modo = req.ia_modo
    if modo is None and req.ai_enabled is not None:
        # Clientes viejos (la app de iOS hasta que se recompile) siguen
        # mandando el booleano: se traduce al modo equivalente.
        modo = "on" if req.ai_enabled else "off"
    if modo is not None:
        if modo not in ("auto", "on", "off"):
            raise HTTPException(status_code=400, detail="ia_modo debe ser auto, on u off")
        # Cualquier cambio explícito del agente borra la pausa temporal:
        # si la acaba de encender, es porque QUIERE que conteste ya.
        cambios = {"ia_modo": modo, "ai_enabled": modo != "off", "ia_pausada_hasta": None}
        guardado = await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"}, cambios)
        if not guardado:
            # Migración pendiente: degradar al booleano clásico.
            await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"},
                           {"ai_enabled": modo != "off"})
    if req.etapa is not None:
        await sb_patch("wa2_contactos", {"id": f"eq.{conv_rows[0]['contacto_id']}"}, {"etapa": req.etapa})
    return {"ok": True}


@router.delete("/mensajes/{mensaje_id}")
async def wa2_borrar_mensaje(mensaje_id: str, request: Request):
    """Borra UN mensaje de la bandeja (y su archivo, si lo tenía).

    Esto no existía. Sin esto, cuando un prospecto ejerce su derecho de
    cancelación —o cuando manda sin que nadie se lo pida una foto de su INE o
    un audio con datos delicados— el agente no tenía absolutamente ninguna
    forma de sacar eso de Broquer. El plazo del artículo 31 de la LFPDPPP le
    corría encima sin poder cumplir.

    Nota: solo borra la copia de Broquer. El mensaje sigue existiendo en el
    WhatsApp de las dos personas; eso no lo controla nadie más que ellas."""
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_mensajes", {"id": f"eq.{mensaje_id}", "user_id": _in_filter(ids),
                                         "select": "id,media_path", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    await _borrar_archivos([rows[0].get("media_path")])
    if not await sb_delete("wa2_mensajes", {"id": f"eq.{mensaje_id}", "user_id": _in_filter(ids)}):
        raise HTTPException(status_code=500, detail="No se pudo borrar el mensaje. Intenta de nuevo.")
    return {"ok": True}


@router.delete("/conversaciones/{conversacion_id}")
async def wa2_borrar_conversacion(conversacion_id: str, request: Request):
    """Borra una conversación completa: sus mensajes, sus archivos y la ficha
    del prospecto en WhatsApp. El Contacto del CRM NO se toca — ese es un
    registro aparte que el agente decide si conserva o no desde Contactos."""
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv = await sb_get("wa2_conversaciones", {"id": f"eq.{conversacion_id}", "user_id": _in_filter(ids),
                                               "select": "id,contacto_id", "limit": "1"})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    archivos, pagina = [], 0
    while pagina < 40:
        lote = await sb_get("wa2_mensajes", {"conversacion_id": f"eq.{conversacion_id}",
                                             "select": "media_path", "limit": "1000",
                                             "offset": str(pagina * 1000)})
        archivos.extend(m.get("media_path") for m in lote)
        if len(lote) < 1000:
            break
        pagina += 1
    await _borrar_archivos(archivos)

    await sb_delete("wa2_mensajes", {"conversacion_id": f"eq.{conversacion_id}"})
    try:
        await sb_delete("wa2_flujo_estados", {"conversacion_id": f"eq.{conversacion_id}"})
    except Exception:
        pass
    await sb_delete("wa2_conversaciones", {"id": f"eq.{conversacion_id}"})
    if conv[0].get("contacto_id"):
        await sb_delete("wa2_contactos", {"id": f"eq.{conv[0]['contacto_id']}"})
    log.info("Conversación %s eliminada por el usuario %s", conversacion_id, user_id)
    return {"ok": True}



class NotaReq(BaseModel):
    texto: str


@router.post("/contactos/{contacto_id}/notas")
async def wa2_agregar_nota(contacto_id: str, req: NotaReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_contactos", {"id": f"eq.{contacto_id}", "user_id": _in_filter(ids),
                                          "select": "notas,contacto_crm_id", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    notas = (rows[0].get("notas") or []) + [{"texto": req.texto, "autor": "agente", "fecha": _now()}]
    await sb_patch("wa2_contactos", {"id": f"eq.{contacto_id}"}, {"notas": notas, "updated_at": _now()})
    await _sincronizar_contacto_crm(user_id, rows[0], {"nota": req.texto})
    return {"ok": True, "notas": notas}


@router.patch("/contactos/{contacto_id}")
async def wa2_contacto_patch(contacto_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    body = await request.json()
    permitido = {k: v for k, v in body.items()
                if k in ("nombre", "presupuesto", "forma_pago", "busca", "temperatura", "score", "etapa", "resumen", "opt_out")}
    # Etiquetas: solo lista de textos cortos, sin repetidos y con tope, para
    # que un cliente no pueda meter basura enorme por el API.
    if "etiquetas" in body and isinstance(body["etiquetas"], list):
        limpias = []
        for e in body["etiquetas"]:
            t = str(e).strip()[:40]
            if t and t not in limpias:
                limpias.append(t)
        permitido["etiquetas"] = limpias[:20]
    if not permitido:
        return {"ok": True}
    permitido["updated_at"] = _now()
    await sb_patch("wa2_contactos", {"id": f"eq.{contacto_id}", "user_id": _in_filter(ids)}, permitido)
    return {"ok": True}


# =============================================================================
# 9.4) AUTOMATIZACIONES — recetas simples: disparador + pasos
#
# El agente arma recetas sin saber nada técnico: "cuando el mensaje contenga
# la palabra PRECIO → responde este texto → ponle la etiqueta interesado".
# Disparadores: 'palabra' (el texto contiene alguna palabra de la lista) o
# 'nuevo' (primer mensaje de un contacto que nunca había escrito).
# Pasos: 'mensaje' (responder un texto fijo), 'etiqueta' (etiquetar al
# contacto) y 'humano' (apagar la IA de esa conversación y avisar al agente).
# Si la receta responde o pasa al humano, la IA ya no contesta ese mensaje.
# =============================================================================
_AUTO_TIPOS = ("mensaje", "etiqueta", "humano", "ia", "pregunta", "opciones")

# Campos donde una pregunta de flujo puede guardar la respuesta del prospecto
_FLUJO_CAMPOS = ("nombre", "presupuesto", "interes", "nota")
_FLUJO_MAX_PASOS_POR_TURNO = 20   # candado anti-loops en saltos de opciones
_FLUJO_CADUCA_HORAS = 24          # un flujo abandonado no revive al día siguiente
_FLUJO_MAX_REINTENTOS = 2         # veces que se re-explica un menú no entendido


# ══════════════════════════════════════════════════════════════════════════
# MOTOR DE FLUJOS — la parte determinista del módulo. Un flujo NUNCA
# improvisa: hace exactamente los pasos que el usuario dibujó, en el orden
# que los dibujó. Es lo que hace que ManyChat "no se equivoque" — y aquí
# convive con la IA: un flujo puede terminar entregándole el chat a la IA
# (paso 'ia') o al agente (paso 'humano').
#
# Pasos que ESPERAN respuesta ('pregunta' y 'opciones') dejan anotado en
# wa2_flujo_estados en qué paso van; el siguiente mensaje del prospecto
# continúa el flujo en vez de irse a la IA.
# ══════════════════════════════════════════════════════════════════════════
from routers.whatsapp_flow_state import _flujo_estado_de_core, _flujo_menu_texto_core, _flujo_estado_guardar_core, _flujo_nota_final_core

async def _flujo_estado_de(conversacion_id: str) -> dict | None:
    return await _flujo_estado_de_core(conversacion_id, sb_get=sb_get)



async def _flujo_estado_guardar(user_id: str, conversacion_id: str, auto_id: str,
                                paso: int, datos: dict) -> None:
    return await _flujo_estado_guardar_core(
        user_id, conversacion_id, auto_id, paso, datos,
        sb_get=sb_get, _now=_now, sb_patch=sb_patch, sb_post=sb_post, log=log,
    )



async def _flujo_estado_borrar(conversacion_id: str) -> None:
    try:
        await sb_delete("wa2_flujo_estados", {"conversacion_id": f"eq.{conversacion_id}"})
    except Exception:
        pass


def _flujo_menu_texto(paso: dict) -> str:
    return _flujo_menu_texto_core(paso)



async def _flujo_nota_final(user_id: str, contacto_id: str, auto_nombre: str, datos: dict) -> None:
    return await _flujo_nota_final_core(
        user_id, contacto_id, auto_nombre, datos,
        sb_get=sb_get, _now=_now, sb_patch=sb_patch,
        _sincronizar_contacto_crm=_sincronizar_contacto_crm, log=log,
    )



async def _flujo_ejecutar(auto: dict, item: dict, numero: dict, user_id: str,
                          desde: int = 0, datos: dict | None = None) -> bool:
    """Ejecuta los pasos del flujo a partir de `desde`. Devuelve True si el
    flujo consumió la conversación (respondió algo o quedó esperando
    respuesta); False si la IA normal debe seguir con este mismo mensaje."""
    acciones = auto.get("acciones") or []
    datos = dict(datos or {})
    i = max(0, desde)
    respondio = False
    ejecutados = 0
    marcado_leido = False

    async def _enviar(texto: str) -> None:
        nonlocal respondio, marcado_leido
        if not marcado_leido:
            await _wa_marcar_leido(numero, item.get("wa_message_id"))
            marcado_leido = True
        wamid = await _wa_send_text(numero, item["wa_id"], texto[:WA_MAX_TEXTO])
        await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"],
                              wamid, "out", "ia", texto[:WA_MAX_TEXTO])
        respondio = True

    while i < len(acciones) and ejecutados < _FLUJO_MAX_PASOS_POR_TURNO:
        ejecutados += 1
        a = acciones[i] or {}
        tipo = a.get("tipo")
        valor = a.get("valor") or ""

        if tipo == "mensaje" and valor:
            await _enviar(valor)
            i += 1
        elif tipo == "etiqueta" and valor:
            try:
                rows = await sb_get("wa2_contactos", {"id": f"eq.{item['contacto_id']}",
                                                      "select": "etiquetas", "limit": "1"})
                tags = (rows[0].get("etiquetas") or []) if rows else []
                if valor not in tags:
                    await sb_patch("wa2_contactos", {"id": f"eq.{item['contacto_id']}"},
                                   {"etiquetas": (tags + [valor])[:20], "updated_at": _now()})
            except Exception as e:
                log.warning("Paso etiqueta del flujo falló: %s", e)
            i += 1
        elif tipo == "humano":
            await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                           {"ai_enabled": False, "ia_modo": "off"})
            await enviar_push(user_id, "Un flujo te pasó un chat",
                              f"El flujo '{auto.get('nombre')}' apagó la IA. Ya te toca a ti.",
                              datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
            await _flujo_estado_borrar(item["conversacion_id"])
            await _flujo_nota_final(user_id, item["contacto_id"], auto.get("nombre") or "", datos)
            return True
        elif tipo == "ia":
            # El flujo termina entregándole la conversación a la IA: se
            # enciende en este chat y la IA contesta ESTE mismo mensaje.
            await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                           {"ia_modo": "on", "ai_enabled": True, "ia_pausada_hasta": None})
            await _flujo_estado_borrar(item["conversacion_id"])
            await _flujo_nota_final(user_id, item["contacto_id"], auto.get("nombre") or "", datos)
            return False
        elif tipo == "pregunta" and valor:
            await _enviar(valor)
            await _flujo_estado_guardar(user_id, item["conversacion_id"], auto["id"], i, datos)
            return True
        elif tipo == "opciones" and (a.get("opciones") or []):
            await _enviar(_flujo_menu_texto(a))
            datos["_intentos"] = 0
            await _flujo_estado_guardar(user_id, item["conversacion_id"], auto["id"], i, datos)
            return True
        else:
            i += 1  # paso vacío o desconocido: se brinca, jamás truena

    # Fin del flujo (o candado anti-loop): se limpia y se entrega lo juntado.
    await _flujo_estado_borrar(item["conversacion_id"])
    await _flujo_nota_final(user_id, item["contacto_id"], auto.get("nombre") or "", datos)
    return respondio


async def _flujo_continuar(estado: dict, item: dict, numero: dict, user_id: str) -> bool:
    """Un flujo estaba esperando respuesta y llegó un mensaje del prospecto.
    Devuelve True si el flujo lo consumió; False si debe seguir el camino
    normal (automatizaciones nuevas / IA)."""
    ult = _parse_ts(estado.get("updated_at"))
    if ult and (datetime.now(timezone.utc) - ult).total_seconds() > _FLUJO_CADUCA_HORAS * 3600:
        await _flujo_estado_borrar(item["conversacion_id"])
        return False
    try:
        autos = await sb_get("wa2_automatizaciones", {"id": f"eq.{estado['automatizacion_id']}",
                                                      "select": "*", "limit": "1"})
    except Exception:
        autos = []
    if not autos or not autos[0].get("activa", True):
        await _flujo_estado_borrar(item["conversacion_id"])
        return False
    auto = autos[0]
    acciones = auto.get("acciones") or []
    paso_idx = int(estado.get("paso") or 0)
    datos = dict(estado.get("datos") or {})
    if paso_idx >= len(acciones):
        await _flujo_estado_borrar(item["conversacion_id"])
        return False
    paso = acciones[paso_idx] or {}
    texto = (item.get("texto") or "").strip()

    if paso.get("tipo") == "pregunta":
        campo = paso.get("guardar") or "nota"
        datos[campo] = texto[:300]
        return await _flujo_ejecutar(auto, item, numero, user_id,
                                     desde=paso_idx + 1, datos=datos)

    if paso.get("tipo") == "opciones":
        ops = paso.get("opciones") or []
        elegido = None
        limpio = texto.lower().strip(".!¡¿? ")
        if limpio.isdigit() and 1 <= int(limpio) <= len(ops):
            elegido = ops[int(limpio) - 1]
        else:
            for op in ops:
                t = (op.get("texto") or "").lower()
                if t and (t in limpio or limpio in t):
                    elegido = op
                    break
        if elegido is None:
            intentos = int(datos.get("_intentos") or 0) + 1
            if intentos > _FLUJO_MAX_REINTENTOS:
                # No entendió dos veces: el flujo se quita de en medio y el
                # mensaje sigue su camino normal (la IA sí sabe conversar).
                await _flujo_estado_borrar(item["conversacion_id"])
                return False
            datos["_intentos"] = intentos
            await _flujo_estado_guardar(user_id, item["conversacion_id"], auto["id"], paso_idx, datos)
            wamid = await _wa_send_text(numero, item["wa_id"],
                                        "Perdón, no te entendí. Respóndeme con el número de una opción:\n"
                                        + _flujo_menu_texto(paso))
            await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"],
                                  wamid, "out", "ia",
                                  "Perdón, no te entendí. Respóndeme con el número de una opción:\n"
                                  + _flujo_menu_texto(paso))
            return True
        datos.pop("_intentos", None)
        datos.setdefault("nota", "")
        # Se anota qué eligió (sirve para la nota final del flujo).
        eleccion = elegido.get("texto") or ""
        datos["nota"] = (datos["nota"] + (" · " if datos["nota"] else "") + f"Eligió: {eleccion}")[:400]
        try:
            ir = int(elegido.get("ir") or 0)
        except Exception:
            ir = 0
        destino = (ir - 1) if ir >= 1 else (paso_idx + 1)
        if destino >= len(acciones):
            destino = len(acciones)  # fuera de rango = terminar el flujo
        return await _flujo_ejecutar(auto, item, numero, user_id, desde=destino, datos=datos)

    # Paso raro (no espera respuesta): se limpia y se sigue normal.
    await _flujo_estado_borrar(item["conversacion_id"])
    return False

# Candado anti-metralleta: la misma receta no se dispara dos veces en la misma
# conversación en menos de este tiempo, aunque el prospecto repita la palabra
# en tres mensajes seguidos. Vive en memoria: suficiente con una instancia.
_AUTO_COOLDOWN_SEG = 120
_AUTO_ULTIMA: dict = {}


class AutomatizacionReq(BaseModel):
    nombre: str
    numero_id: str | None = None
    disparador: str = "palabra"
    palabras: list[str] = []
    acciones: list[dict] = []
    activa: bool = True


from routers.whatsapp_automation_policy import _limpiar_automatizacion_core

def _limpiar_automatizacion(req: AutomatizacionReq) -> dict:
    return _limpiar_automatizacion_core(
        req, _AUTO_TIPOS=_AUTO_TIPOS, _FLUJO_CAMPOS=_FLUJO_CAMPOS,
        HTTPException=HTTPException,
    )



@router.get("/automatizaciones")
async def wa2_automatizaciones_list(request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_automatizaciones", {"user_id": _in_filter(ids), "select": "*",
                                                 "order": "created_at.desc", "limit": "100"})
    return {"automatizaciones": rows}


@router.post("/automatizaciones")
async def wa2_automatizacion_crear(req: AutomatizacionReq, request: Request):
    user_id = await _require_user(request)
    fila = _limpiar_automatizacion(req)
    if fila["numero_id"]:
        ids = await _ids_visibles(user_id)
        n = await sb_get("wa2_numeros", {"id": f"eq.{fila['numero_id']}",
                                         "user_id": _in_filter(ids), "select": "id", "limit": "1"})
        if not n:
            raise HTTPException(status_code=404, detail="Número no encontrado")
    fila.update({"user_id": user_id, "veces_usada": 0,
                 "created_at": _now(), "updated_at": _now()})
    creado = await sb_post("wa2_automatizaciones", fila)
    if not creado:
        raise HTTPException(status_code=500,
                            detail="No se pudo guardar. ¿Ya corriste la migración de automatizaciones?")
    return {"ok": True}


@router.patch("/automatizaciones/{auto_id}")
async def wa2_automatizacion_patch(auto_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    body = await request.json()
    permitido = {}
    if "activa" in body:
        permitido["activa"] = bool(body["activa"])
    # Editar el flujo completo (nombre, disparador, pasos): pasa por la MISMA
    # validación que al crearlo — cero caminos alternos donde equivocarse.
    if any(k in body for k in ("nombre", "disparador", "palabras", "acciones", "numero_id")):
        actual_rows = await sb_get("wa2_automatizaciones",
                                   {"id": f"eq.{auto_id}", "user_id": _in_filter(ids),
                                    "select": "*", "limit": "1"})
        if not actual_rows:
            raise HTTPException(status_code=404, detail="Automatización no encontrada")
        actual = actual_rows[0]
        req = AutomatizacionReq(
            nombre=body.get("nombre", actual.get("nombre") or ""),
            numero_id=body.get("numero_id", actual.get("numero_id")),
            disparador=body.get("disparador", actual.get("disparador") or "palabra"),
            palabras=body.get("palabras", actual.get("palabras") or []),
            acciones=body.get("acciones", actual.get("acciones") or []),
            activa=bool(body.get("activa", actual.get("activa", True))),
        )
        permitido.update(_limpiar_automatizacion(req))
    if not permitido:
        return {"ok": True}
    permitido["updated_at"] = _now()
    await sb_patch("wa2_automatizaciones", {"id": f"eq.{auto_id}", "user_id": _in_filter(ids)}, permitido)
    return {"ok": True}


@router.delete("/automatizaciones/{auto_id}")
async def wa2_automatizacion_delete(auto_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    await sb_delete("wa2_automatizaciones", {"id": f"eq.{auto_id}", "user_id": _in_filter(ids)})
    return {"ok": True}


async def _correr_automatizaciones(item: dict, numero: dict, user_id: str) -> bool:
    """Evalúa las recetas del usuario para este mensaje. Devuelve True si
    alguna receta respondió o pasó el chat al humano (la IA ya no contesta)."""
    autos = await sb_get("wa2_automatizaciones",
                         {"user_id": f"eq.{numero['user_id']}", "activa": "eq.true",
                          "or": f"(numero_id.is.null,numero_id.eq.{numero['id']})",
                          "select": "*", "limit": "100"})
    if not autos:
        return False

    texto = (item.get("texto") or "").lower()
    es_nuevo = None  # se calcula solo si alguna receta lo necesita
    silenciar_ia = False
    ahora = datetime.now(timezone.utc).timestamp()

    for auto in autos:
        disparador = auto.get("disparador")
        if disparador == "nuevo":
            if es_nuevo is None:
                entrantes = await sb_get("wa2_mensajes",
                                         {"conversacion_id": f"eq.{item['conversacion_id']}",
                                          "direction": "eq.in", "select": "id", "limit": "2"})
                es_nuevo = len(entrantes) <= 1
            if not es_nuevo:
                continue
        elif disparador == "nuevo_3m":
            # Cliente nuevo en el sentido amplio: nunca había escrito, o
            # llevaba más de 3 meses sin escribir (el snapshot se tomó antes
            # de guardar este mensaje, así que es la fecha correcta).
            prev_dt = _parse_ts(item.get("prev_inbound_at"))
            if prev_dt is not None and (datetime.now(timezone.utc) - prev_dt).days < 90:
                continue
        else:
            palabras = auto.get("palabras") or []
            if not any(p and str(p).lower() in texto for p in palabras):
                continue

        llave = f"{item['conversacion_id']}|{auto['id']}"
        if ahora - _AUTO_ULTIMA.get(llave, 0) < _AUTO_COOLDOWN_SEG:
            continue
        _AUTO_ULTIMA[llave] = ahora
        if len(_AUTO_ULTIMA) > 5000:
            for k in list(_AUTO_ULTIMA.keys())[:1000]:
                _AUTO_ULTIMA.pop(k, None)

        # Todos los pasos (viejos y nuevos) corren por el MISMO motor de
        # flujos: una sola implementación, un solo lugar donde equivocarse.
        try:
            if await _flujo_ejecutar(auto, item, numero, user_id):
                silenciar_ia = True
        except Exception as e:
            log.warning("Flujo %s falló: %s", auto.get("id"), e)

        try:
            await sb_patch("wa2_automatizaciones", {"id": f"eq.{auto['id']}"},
                           {"veces_usada": (auto.get("veces_usada") or 0) + 1, "updated_at": _now()})
        except Exception:
            pass

        if silenciar_ia:
            # Un flujo ya tomó la conversación (respondió o quedó esperando):
            # ningún otro flujo se le encima. Dos bots en un chat es el mismo
            # error que dos personas en un chat.
            break

    return silenciar_ia


# =============================================================================
# 9.5) CAMPAÑAS — envío masivo de una plantilla aprobada a una audiencia
#
# La audiencia son los contactos de UN número (todos, o solo los que tengan
# cierta etiqueta), quitando siempre: gente sin wa_id, gente dada de baja
# (opt_out) y el propio asesor. El envío corre en segundo plano, uno por uno
# con una pausa corta, y cada envío queda registrado en wa2_campana_envios.
# Cada mensaje que sale también se guarda en su conversación de la bandeja,
# para que el agente vea qué se le mandó a quién.
# =============================================================================
class CampanaAudienciaReq(BaseModel):
    numero_id: str
    etiqueta: str | None = None


class CampanaCrearReq(BaseModel):
    numero_id: str
    nombre: str
    plantilla: str
    idioma: str = "es_MX"
    variables: list[str] = []
    etiqueta: str | None = None


from routers.whatsapp_campaign_audience import _audiencia_campana_core

async def _audiencia_campana(numero: dict, etiqueta: str | None) -> list:
    return await _audiencia_campana_core(
        numero, etiqueta, sb_get=sb_get, json=json, _es_asesor=_es_asesor,
    )



async def _numero_visible(request: Request, numero_id: str) -> tuple[str, dict]:
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}",
                                        "user_id": _in_filter(ids),
                                        "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    return user_id, rows[0]


@router.get("/etiquetas")
async def wa2_etiquetas_list(request: Request):
    """Todas las etiquetas distintas que el usuario ha puesto a sus contactos
    de WhatsApp — alimenta el selector de audiencia de campañas."""
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_contactos", {"user_id": _in_filter(ids),
                                          "select": "etiquetas", "limit": "5000"})
    etiquetas = sorted({str(e).strip() for c in rows
                        for e in (c.get("etiquetas") or []) if str(e).strip()})
    return {"etiquetas": etiquetas}


@router.post("/campanas/audiencia")
async def wa2_campana_audiencia(req: CampanaAudienciaReq, request: Request):
    """Cuenta (sin enviar nada) a cuánta gente le llegaría la campaña."""
    _, numero = await _numero_visible(request, req.numero_id)
    audiencia = await _audiencia_campana(numero, (req.etiqueta or "").strip() or None)
    return {"total": len(audiencia), "tope": WA2_CAMPANA_TOPE}


@router.get("/campanas")
async def wa2_campanas_list(request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_campanas", {"user_id": _in_filter(ids), "select": "*",
                                         "order": "created_at.desc", "limit": "30"})
    return {"campanas": rows}


@router.get("/campanas/{campana_id}")
async def wa2_campana_detalle(campana_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_campanas", {"id": f"eq.{campana_id}",
                                         "user_id": _in_filter(ids),
                                         "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    fallidos = await sb_get("wa2_campana_envios", {"campana_id": f"eq.{campana_id}",
                                                   "estado": "eq.fallido",
                                                   "select": "nombre,wa_id,error",
                                                   "limit": "200"})
    return {"campana": rows[0], "fallidos": fallidos}


@router.post("/campanas")
async def wa2_campana_crear(req: CampanaCrearReq, request: Request, background: BackgroundTasks):
    _, numero = await _numero_visible(request, req.numero_id)

    nombre = (req.nombre or "").strip()[:80]
    plantilla = (req.plantilla or "").strip()
    if not nombre or not plantilla:
        raise HTTPException(status_code=400, detail="Falta el nombre de la campaña o la plantilla.")

    etiqueta = (req.etiqueta or "").strip() or None
    audiencia = await _audiencia_campana(numero, etiqueta)
    if not audiencia:
        raise HTTPException(status_code=400,
                            detail="No hay contactos en esa audiencia (o todos pidieron baja).")
    if len(audiencia) > WA2_CAMPANA_TOPE:
        raise HTTPException(status_code=400,
                            detail=f"La audiencia tiene {len(audiencia)} contactos y el tope por "
                                   f"campaña es {WA2_CAMPANA_TOPE}. Usa una etiqueta para segmentarla.")

    variables = [str(v)[:200] for v in (req.variables or [])][:10]
    fila = {"user_id": numero["user_id"], "numero_id": numero["id"], "nombre": nombre,
            "plantilla": plantilla, "idioma": (req.idioma or "es_MX")[:12],
            "variables": variables, "etiqueta": etiqueta, "estado": "enviando",
            "total": len(audiencia), "enviados": 0, "fallidos": 0, "created_at": _now()}
    creado = await sb_post("wa2_campanas", fila)
    if not creado:
        raise HTTPException(status_code=500,
                            detail="No se pudo crear la campaña. ¿Ya corriste la migración de campañas?")
    campana_id = (creado[0] if isinstance(creado, list) else creado).get("id")

    background.add_task(_correr_campana, campana_id, numero, audiencia,
                        plantilla, (req.idioma or "es_MX"), variables)
    return {"ok": True, "campana_id": campana_id, "total": len(audiencia)}


def _variables_para(contacto: dict, variables: list) -> list:
    """Sustituye el comodín {nombre} por el primer nombre real del contacto —
    la única personalización automática de la capa estándar."""
    listas = []
    for v in variables:
        if str(v).strip().lower() in ("{nombre}", "{{nombre}}"):
            primero = (contacto.get("nombre") or "").strip().split(" ")[0]
            listas.append(primero.title() if primero else "Hola")
        else:
            listas.append(str(v))
    return listas


async def _correr_campana(campana_id: str, numero: dict, audiencia: list,
                          plantilla: str, idioma: str, variables: list):
    enviados = fallidos = 0
    async with httpx.AsyncClient(timeout=20) as c:
        for i, ct in enumerate(audiencia):
            vars_ct = _variables_para(ct, variables)
            componentes = []
            if vars_ct:
                componentes.append({"type": "body",
                                    "parameters": [{"type": "text", "text": v} for v in vars_ct]})
            wamid, err = None, ""
            try:
                r = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                                 headers={"Authorization": f"Bearer {numero['access_token']}"},
                                 json={"messaging_product": "whatsapp", "to": ct["wa_id"],
                                       "type": "template",
                                       "template": {"name": plantilla,
                                                    "language": {"code": idioma},
                                                    "components": componentes}})
                if r.status_code < 400:
                    msgs = r.json().get("messages") or []
                    wamid = msgs[0].get("id") if msgs else None
                else:
                    try:
                        err = (r.json().get("error", {}).get("message") or "")[:200]
                    except Exception:
                        err = r.text[:200]
                    if not err:
                        err = f"Meta respondió {r.status_code}"
            except Exception as e:
                err = str(e)[:200]

            ok = not err
            try:
                await sb_post("wa2_campana_envios",
                              {"campana_id": campana_id, "user_id": numero["user_id"],
                               "contacto_id": ct["id"], "wa_id": ct.get("wa_id"),
                               "nombre": ct.get("nombre"),
                               "estado": "enviado" if ok else "fallido",
                               "error": err or None, "created_at": _now()})
            except Exception:
                pass

            if ok:
                enviados += 1
                # Reflejar el envío en la bandeja, en la conversación de esa
                # persona (si no tenía, se crea con la IA apagada: fue un
                # masivo, no una conversación que la IA deba retomar sola).
                try:
                    conv = await _get_o_crea_conversacion(numero["user_id"], numero["id"],
                                                          ct["id"], ia_default=False)
                    resumen = f"[Campaña · plantilla {plantilla}]"
                    await _guardar_mensaje(numero["user_id"], ct["id"], conv["id"],
                                          wamid, "out", "agente", resumen)
                except Exception:
                    pass
            else:
                fallidos += 1
                log.warning("Campaña %s: fallo con %s: %s", campana_id, ct.get("wa_id"), err)

            if (i + 1) % 10 == 0:
                try:
                    await sb_patch("wa2_campanas", {"id": f"eq.{campana_id}"},
                                   {"enviados": enviados, "fallidos": fallidos})
                except Exception:
                    pass
            # Pausa corta entre envíos: no saturar el API de Meta ni parecer spam.
            await asyncio.sleep(0.5)

    try:
        await sb_patch("wa2_campanas", {"id": f"eq.{campana_id}"},
                       {"enviados": enviados, "fallidos": fallidos,
                        "estado": "terminada", "terminado_at": _now()})
    except Exception:
        pass
    await enviar_push(numero.get("user_id"), "Campaña terminada",
                      f"Se enviaron {enviados} mensajes"
                      + (f" ({fallidos} fallaron)" if fallidos else "") + ".",
                      datos={"tipo": "whatsapp"})


# =============================================================================
# 10) ESTADÍSTICAS — agregados para el módulo de Estadísticas
#
# El módulo de Estadísticas no puede pegarle directo a wa2_* desde el navegador
# (esas tablas viven detrás del service key, igual que el resto de la bandeja).
# Este endpoint devuelve TODO ya agregado y para las cuatro ventanas de tiempo
# de un solo golpe, para que el frontend cambie de periodo sin volver a pedir.
# =============================================================================
_VENTANAS_ESTAD = {"semana": 7, "mes": 30, "trimestre": 90, "todo": 0}


async def _sb_diag(table: str, params: dict) -> tuple[list, str]:
    """Diagnostic read: unlike sb_get, keep the database error text visible."""
    try:
        data = await get_rows(table, params, timeout=25)
        return data, ""
    except httpx.HTTPStatusError as exc:
        r = exc.response
        return [], f"{r.status_code}: {r.text[:200]}"
    except Exception as e:
        return [], str(e)[:200]


async def _sb_get_paginado(table: str, params: dict, tope: int = 40000,
                           paralelo: int = 6) -> tuple[list, str]:
    """PostgREST corta en 1000 filas. Para estadísticas necesitamos el historial
    completo, así que se pagina — pero EN PARALELO. En serie, un historial de
    30 mil mensajes son 30 viajes de ida y vuelta y Railway corta la conexión
    antes de terminar (el navegador lo ve como 'Failed to fetch').
    Devuelve (filas, error)."""
    salida: list = []
    error = ""
    pagina = 1000
    bloque = 0
    while len(salida) < tope and bloque < 40:
        tareas = []
        for k in range(paralelo):
            p = dict(params)
            p["limit"] = str(pagina)
            p["offset"] = str((bloque * paralelo + k) * pagina)
            tareas.append(_sb_diag(table, p))
        resultados = await asyncio.gather(*tareas, return_exceptions=True)
        traidas = 0
        for res in resultados:
            if isinstance(res, Exception):
                error = error or str(res)[:200]
                continue
            filas, err = res
            if err:
                error = error or err
                continue
            salida.extend(filas)
            traidas += len(filas)
        if error and not salida:
            break
        if traidas < pagina * paralelo:
            break
        bloque += 1
    return salida[:tope], error





@router.get("/estadisticas")
async def wa2_estadisticas(request: Request, zona: str | None = None):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    filtro = _in_filter(ids)
    zona = zona or _ZONA_DEFAULT

    # Las tablas chicas se piden con select=* a propósito: si una columna
    # opcional todavía no existe en la base del agente (una migración que no se
    # corrió), un select con nombres explícitos devuelve 400 y TODO se ve en
    # cero sin decir por qué. Con * no hay columna que pueda faltar.
    (numeros, e_num), (contactos, e_con), (conversaciones, e_conv), (mensajes, e_msg) = await asyncio.gather(
        _sb_diag("wa2_numeros", {"user_id": filtro, "select": "*"}),
        _sb_get_paginado("wa2_contactos", {"user_id": filtro, "order": "id.asc", "select": "*"}, tope=20000),
        _sb_get_paginado("wa2_conversaciones", {"user_id": filtro, "order": "id.asc", "select": "*"}, tope=20000),
        _sb_get_paginado("wa2_mensajes", {
            "user_id": filtro, "order": "id.asc",
            "select": "conversacion_id,direction,sender,created_at"}),
    )
    # Respaldo: si el select angosto de mensajes falló (nombre de columna
    # distinto), se reintenta con * antes de darse por vencido.
    if e_msg and not mensajes:
        mensajes, e_msg2 = await _sb_get_paginado(
            "wa2_mensajes", {"user_id": filtro, "order": "id.asc", "select": "*"})
        if mensajes:
            e_msg = ""
        else:
            e_msg = e_msg2 or e_msg

    for n in numeros:
        n.pop("access_token", None)

    diagnostico = {
        "user_ids": len(ids),
        "numeros": len(numeros), "contactos": len(contactos),
        "conversaciones": len(conversaciones), "mensajes": len(mensajes),
        "errores": {k: v for k, v in {
            "wa2_numeros": e_num, "wa2_contactos": e_con,
            "wa2_conversaciones": e_conv, "wa2_mensajes": e_msg,
        }.items() if v},
    }
    if diagnostico["errores"]:
        log.error("estadisticas whatsapp2: %s", diagnostico["errores"])

    ahora = datetime.now(timezone.utc)
    ventanas = {
        nombre: _agrega_ventana(dias, ahora, zona, contactos, conversaciones, mensajes, numeros)
        for nombre, dias in _VENTANAS_ESTAD.items()
    }
    return {
        "ok": True,
        "zona": zona,
        "generado": _now(),
        "numeros_conectados": len(numeros),
        "diagnostico": diagnostico,
        "ventanas": ventanas,
    }
