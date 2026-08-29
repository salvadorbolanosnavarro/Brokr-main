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


from routers.whatsapp_concurrency import lock_conv as _lock_conv_core

def _lock_conv(conversacion_id: str) -> asyncio.Lock:
    return _lock_conv_core(conversacion_id, _LOCKS=_LOCKS, asyncio=asyncio)


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









from routers.whatsapp_manual_pause import _pausar_por_respuesta_manual_core

async def _pausar_por_respuesta_manual(conv: dict, numero: dict, entren: dict | None = None) -> dict:
    return await _pausar_por_respuesta_manual_core(
        conv, numero, entren,
        _entrenamiento_de=_entrenamiento_de, _modo_conv=_modo_conv,
        datetime=datetime, timezone=timezone, timedelta=timedelta, sb_patch=sb_patch,
    )





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


from routers.whatsapp_agenda_api import wa2_agendar_core

@router.post("/agendar")
async def wa2_agendar(req: AgendarReq, request: Request):
    return await wa2_agendar_core(
        req, request,
        _require_user=_require_user, _ids_visibles=_ids_visibles, sb_get=sb_get,
        _in_filter=_in_filter, HTTPException=HTTPException, sb_patch=sb_patch,
        _entrenamiento_de=_entrenamiento_de, _fecha_hora_utc_iso=_fecha_hora_utc_iso,
        sb_post=sb_post, _construir_ics=_construir_ics, _wa_send_document=_wa_send_document,
    )



# =============================================================================
# 6) ENVÍO POR WHATSAPP (Cloud API)
# =============================================================================
from routers.whatsapp_token_health import _revisar_token_core

async def _revisar_token(numero: dict, err: dict | None) -> None:
    return await _revisar_token_core(
        numero, err, sb_patch=sb_patch, _now=_now, enviar_push=enviar_push, log=log,
    )



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


from routers.whatsapp_background import _procesar_en_segundo_plano_core

async def _procesar_en_segundo_plano(item: dict):
    return await _procesar_en_segundo_plano_core(
        item, sb_get=sb_get, enviar_push=enviar_push,
        _flujo_estado_de=_flujo_estado_de, _flujo_continuar=_flujo_continuar,
        log=log, _correr_automatizaciones=_correr_automatizaciones,
        WA2_DEBOUNCE=WA2_DEBOUNCE, asyncio=asyncio, _lock_conv=_lock_conv,
        _broq_asesor=_broq_asesor, _responder_conversacion=_responder_conversacion,
    )



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



from routers.whatsapp_prospect_brain import _responder_conversacion_core

async def _responder_conversacion(item: dict, numero: dict, user_id: str):
    return await _responder_conversacion_core(
        item, numero, user_id,
        sb_get=sb_get, _entrenamiento_de=_entrenamiento_de, _parse_ts=_parse_ts,
        datetime=datetime, timezone=timezone, sb_patch=sb_patch, _ia_decide=_ia_decide,
        _en_horario=_en_horario, _wa_marcar_leido=_wa_marcar_leido, _wa_send_text=_wa_send_text,
        _guardar_mensaje=_guardar_mensaje, enviar_push=enviar_push, WA2_TOPE_IA=WA2_TOPE_IA,
        HISTORY_LIMIT=HISTORY_LIMIT, _perfil_agente=_perfil_agente, recepcion2_responde=recepcion2_responde,
        _now=_now, _sincronizar_contacto_crm=_sincronizar_contacto_crm,
        _parsear_presupuesto=_parsear_presupuesto, _buscar_inmuebles=_buscar_inmuebles, asyncio=asyncio,
        _generar_ficha_pdf=_generar_ficha_pdf, _propiedad_para_ficha=_propiedad_para_ficha,
        _texto_inmueble=_texto_inmueble, _wa_send_document_link=_wa_send_document_link,
        _resolver_inmueble_id=_resolver_inmueble_id, sb_post=sb_post,
        _fecha_hora_utc_iso=_fecha_hora_utc_iso, _construir_ics=_construir_ics,
        _wa_send_document=_wa_send_document, _alta_inmueble=_alta_inmueble, log=log, _money=_money,
    )



# =============================================================================
# 9) BANDEJA — conversaciones, mensajes, notas, handoff manual, envío manual
# =============================================================================
from routers.whatsapp_inbox_read import (
    wa2_conversaciones_list_core, wa2_mensajes_list_core,
)

@router.get("/conversaciones")
async def wa2_conversaciones_list(request: Request, numero_id: str | None = None):
    return await wa2_conversaciones_list_core(
        request, numero_id,
        _require_user=_require_user, _ids_visibles=_ids_visibles,
        _in_filter=_in_filter, sb_get=sb_get, log=log,
    )



@router.get("/mensajes")
async def wa2_mensajes_list(request: Request, conversacion_id: str,
                            limit: int = 30, before: str | None = None, after: str | None = None):
    return await wa2_mensajes_list_core(
        request, conversacion_id, limit, before, after,
        _require_user=_require_user, _ids_visibles=_ids_visibles,
        _in_filter=_in_filter, sb_get=sb_get,
    )



class EnviarManualReq(BaseModel):
    conversacion_id: str
    texto: str


from routers.whatsapp_inbox_write import wa2_enviar_manual_core, wa2_lectura_core

@router.post("/mensajes")
async def wa2_enviar_manual(req: EnviarManualReq, request: Request):
    return await wa2_enviar_manual_core(
        req, request,
        _require_user=_require_user, _ids_visibles=_ids_visibles, sb_get=sb_get,
        _in_filter=_in_filter, HTTPException=HTTPException, WA_MAX_TEXTO=WA_MAX_TEXTO,
        _wa_send_text_detallado=_wa_send_text_detallado, _guardar_mensaje=_guardar_mensaje,
        _pausar_por_respuesta_manual=_pausar_por_respuesta_manual,
    )



class LecturaReq(BaseModel):
    no_leida: bool = False


@router.post("/conversaciones/{conversacion_id}/lectura")
async def wa2_lectura(conversacion_id: str, req: LecturaReq, request: Request):
    return await wa2_lectura_core(
        conversacion_id, req, request,
        _require_user=_require_user, _ids_visibles=_ids_visibles, sb_get=sb_get,
        _in_filter=_in_filter, HTTPException=HTTPException, sb_patch=sb_patch,
        _wa_marcar_leido=_wa_marcar_leido,
    )



class ConvPatchReq(BaseModel):
    ai_enabled: bool | None = None
    ia_modo: str | None = None      # 'auto' | 'on' | 'off'
    etapa: str | None = None


from routers.whatsapp_conversation_write import wa2_conversacion_patch_core

@router.patch("/conversaciones/{conversacion_id}")
async def wa2_conversacion_patch(conversacion_id: str, req: ConvPatchReq, request: Request):
    return await wa2_conversacion_patch_core(
        conversacion_id, req, request,
        _require_user=_require_user, _ids_visibles=_ids_visibles, sb_get=sb_get,
        _in_filter=_in_filter, HTTPException=HTTPException, sb_patch=sb_patch,
    )



from routers.whatsapp_delete_core import (
    wa2_borrar_mensaje_core, wa2_borrar_conversacion_core,
)

@router.delete("/mensajes/{mensaje_id}")
async def wa2_borrar_mensaje(mensaje_id: str, request: Request):
    return await wa2_borrar_mensaje_core(
        mensaje_id, request, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,
        _borrar_archivos=_borrar_archivos, sb_delete=sb_delete,
    )



@router.delete("/conversaciones/{conversacion_id}")
async def wa2_borrar_conversacion(conversacion_id: str, request: Request):
    return await wa2_borrar_conversacion_core(
        conversacion_id, request, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,
        _borrar_archivos=_borrar_archivos, sb_delete=sb_delete, log=log,
    )




class NotaReq(BaseModel):
    texto: str


from routers.whatsapp_contact_write import (
    wa2_agregar_nota_core, wa2_contacto_patch_core,
)

@router.post("/contactos/{contacto_id}/notas")
async def wa2_agregar_nota(contacto_id: str, req: NotaReq, request: Request):
    return await wa2_agregar_nota_core(
        contacto_id, req, request,
        _require_user=_require_user, _ids_visibles=_ids_visibles, sb_get=sb_get,
        _in_filter=_in_filter, HTTPException=HTTPException, _now=_now, sb_patch=sb_patch,
        _sincronizar_contacto_crm=_sincronizar_contacto_crm,
    )



@router.patch("/contactos/{contacto_id}")
async def wa2_contacto_patch(contacto_id: str, request: Request):
    return await wa2_contacto_patch_core(
        contacto_id, request,
        _require_user=_require_user, _ids_visibles=_ids_visibles, _in_filter=_in_filter,
        _now=_now, sb_patch=sb_patch,
    )



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
from routers.whatsapp_flow_state import _flujo_estado_de_core, _flujo_menu_texto_core, _flujo_estado_guardar_core, _flujo_nota_final_core, _flujo_estado_borrar_core

async def _flujo_estado_de(conversacion_id: str) -> dict | None:
    return await _flujo_estado_de_core(conversacion_id, sb_get=sb_get)



async def _flujo_estado_guardar(user_id: str, conversacion_id: str, auto_id: str,
                                paso: int, datos: dict) -> None:
    return await _flujo_estado_guardar_core(
        user_id, conversacion_id, auto_id, paso, datos,
        sb_get=sb_get, _now=_now, sb_patch=sb_patch, sb_post=sb_post, log=log,
    )



async def _flujo_estado_borrar(conversacion_id: str) -> None:
    return await _flujo_estado_borrar_core(conversacion_id, sb_delete=sb_delete)



def _flujo_menu_texto(paso: dict) -> str:
    return _flujo_menu_texto_core(paso)



async def _flujo_nota_final(user_id: str, contacto_id: str, auto_nombre: str, datos: dict) -> None:
    return await _flujo_nota_final_core(
        user_id, contacto_id, auto_nombre, datos,
        sb_get=sb_get, _now=_now, sb_patch=sb_patch,
        _sincronizar_contacto_crm=_sincronizar_contacto_crm, log=log,
    )



from routers.whatsapp_flow_engine import _flujo_ejecutar_core

async def _flujo_ejecutar(auto: dict, item: dict, numero: dict, user_id: str,
                          desde: int = 0, datos: dict | None = None) -> bool:
    return await _flujo_ejecutar_core(
        auto, item, numero, user_id, desde, datos,
        WA_MAX_TEXTO=WA_MAX_TEXTO, _wa_marcar_leido=_wa_marcar_leido,
        _wa_send_text=_wa_send_text, _guardar_mensaje=_guardar_mensaje,
        _FLUJO_MAX_PASOS_POR_TURNO=_FLUJO_MAX_PASOS_POR_TURNO, sb_get=sb_get,
        sb_patch=sb_patch, _now=_now, log=log, enviar_push=enviar_push,
        _flujo_estado_borrar=_flujo_estado_borrar, _flujo_nota_final=_flujo_nota_final,
        _flujo_estado_guardar=_flujo_estado_guardar, _flujo_menu_texto=_flujo_menu_texto,
    )



from routers.whatsapp_flow_continue import _flujo_continuar_core

async def _flujo_continuar(estado: dict, item: dict, numero: dict, user_id: str) -> bool:
    return await _flujo_continuar_core(
        estado, item, numero, user_id, _parse_ts=_parse_ts, datetime=datetime,
        timezone=timezone, _FLUJO_CADUCA_HORAS=_FLUJO_CADUCA_HORAS,
        _flujo_estado_borrar=_flujo_estado_borrar, sb_get=sb_get,
        _flujo_ejecutar=_flujo_ejecutar, _FLUJO_MAX_REINTENTOS=_FLUJO_MAX_REINTENTOS,
        _flujo_estado_guardar=_flujo_estado_guardar, _wa_send_text=_wa_send_text,
        _flujo_menu_texto=_flujo_menu_texto, _guardar_mensaje=_guardar_mensaje,
    )


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



from routers.whatsapp_automation_write import (
    wa2_automatizaciones_list_core, wa2_automatizacion_crear_core,
    wa2_automatizacion_patch_core,
)

@router.get("/automatizaciones")
async def wa2_automatizaciones_list(request: Request):
    return await wa2_automatizaciones_list_core(
        request, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter,
    )



@router.post("/automatizaciones")
async def wa2_automatizacion_crear(req: AutomatizacionReq, request: Request):
    return await wa2_automatizacion_crear_core(
        req, request, _require_user=_require_user,
        _limpiar_automatizacion=_limpiar_automatizacion, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,
        _now=_now, sb_post=sb_post,
    )



@router.patch("/automatizaciones/{auto_id}")
async def wa2_automatizacion_patch(auto_id: str, request: Request):
    return await wa2_automatizacion_patch_core(
        auto_id, request, _require_user=_require_user, _ids_visibles=_ids_visibles,
        _in_filter=_in_filter, sb_get=sb_get, HTTPException=HTTPException,
        AutomatizacionReq=AutomatizacionReq, _limpiar_automatizacion=_limpiar_automatizacion,
        _now=_now, sb_patch=sb_patch,
    )



from routers.whatsapp_automation_delete import wa2_automatizacion_delete_core

@router.delete("/automatizaciones/{auto_id}")
async def wa2_automatizacion_delete(auto_id: str, request: Request):
    return await wa2_automatizacion_delete_core(
        auto_id, request, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_delete=sb_delete, _in_filter=_in_filter,
    )



from routers.whatsapp_automation_runner import _correr_automatizaciones_core

async def _correr_automatizaciones(item: dict, numero: dict, user_id: str) -> bool:
    return await _correr_automatizaciones_core(
        item, numero, user_id, sb_get=sb_get, datetime=datetime, timezone=timezone,
        _parse_ts=_parse_ts, _AUTO_ULTIMA=_AUTO_ULTIMA,
        _AUTO_COOLDOWN_SEG=_AUTO_COOLDOWN_SEG, _flujo_ejecutar=_flujo_ejecutar,
        log=log, sb_patch=sb_patch, _now=_now,
    )



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



from routers.whatsapp_campaign_access import _numero_visible_core

async def _numero_visible(request: Request, numero_id: str) -> tuple[str, dict]:
    return await _numero_visible_core(
        request, numero_id, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,
    )



from routers.whatsapp_campaign_read import (
    wa2_etiquetas_list_core, wa2_campanas_list_core, wa2_campana_detalle_core,
)

@router.get("/etiquetas")
async def wa2_etiquetas_list(request: Request):
    return await wa2_etiquetas_list_core(
        request, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter,
    )



from routers.whatsapp_campaign_preview import wa2_campana_audiencia_core

@router.post("/campanas/audiencia")
async def wa2_campana_audiencia(req: CampanaAudienciaReq, request: Request):
    return await wa2_campana_audiencia_core(
        req, request, _numero_visible=_numero_visible,
        _audiencia_campana=_audiencia_campana, WA2_CAMPANA_TOPE=WA2_CAMPANA_TOPE,
    )



@router.get("/campanas")
async def wa2_campanas_list(request: Request):
    return await wa2_campanas_list_core(
        request, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter,
    )



@router.get("/campanas/{campana_id}")
async def wa2_campana_detalle(campana_id: str, request: Request):
    return await wa2_campana_detalle_core(
        campana_id, request, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,
    )



from routers.whatsapp_campaign_create import wa2_campana_crear_core

@router.post("/campanas")
async def wa2_campana_crear(req: CampanaCrearReq, request: Request, background: BackgroundTasks):
    return await wa2_campana_crear_core(
        req, request, background,
        _numero_visible=_numero_visible, _audiencia_campana=_audiencia_campana,
        WA2_CAMPANA_TOPE=WA2_CAMPANA_TOPE, HTTPException=HTTPException,
        _now=_now, sb_post=sb_post, _correr_campana=_correr_campana,
    )



from routers.whatsapp_campaign_variables import variables_para as _variables_para_core

def _variables_para(contacto: dict, variables: list) -> list:
    return _variables_para_core(contacto, variables)



from routers.whatsapp_campaign_runner import _correr_campana_core

async def _correr_campana(campana_id: str, numero: dict, audiencia: list,
                          plantilla: str, idioma: str, variables: list):
    return await _correr_campana_core(
        campana_id, numero, audiencia, plantilla, idioma, variables,
        httpx=httpx, GRAPH_API=GRAPH_API, _variables_para=_variables_para,
        sb_post=sb_post, _now=_now,
        _get_o_crea_conversacion=_get_o_crea_conversacion,
        _guardar_mensaje=_guardar_mensaje, log=log, sb_patch=sb_patch,
        asyncio=asyncio, enviar_push=enviar_push,
    )



# =============================================================================
# 10) ESTADÍSTICAS — agregados para el módulo de Estadísticas
#
# El módulo de Estadísticas no puede pegarle directo a wa2_* desde el navegador
# (esas tablas viven detrás del service key, igual que el resto de la bandeja).
# Este endpoint devuelve TODO ya agregado y para las cuatro ventanas de tiempo
# de un solo golpe, para que el frontend cambie de periodo sin volver a pedir.
# =============================================================================
_VENTANAS_ESTAD = {"semana": 7, "mes": 30, "trimestre": 90, "todo": 0}


from routers.whatsapp_stats_io import (
    sb_diag_core as _sb_diag_core,
    sb_get_paginado_core as _sb_get_paginado_core,
)

async def _sb_diag(table: str, params: dict) -> tuple[list, str]:
    return await _sb_diag_core(table, params, get_rows=get_rows, httpx=httpx)



async def _sb_get_paginado(table: str, params: dict, tope: int = 40000,
                           paralelo: int = 6) -> tuple[list, str]:
    return await _sb_get_paginado_core(
        table, params, tope, paralelo, _sb_diag=_sb_diag, asyncio=asyncio,
    )






from routers.whatsapp_stats_api import wa2_estadisticas_core

@router.get("/estadisticas")
async def wa2_estadisticas(request: Request, zona: str | None = None):
    return await wa2_estadisticas_core(
        request, zona,
        _require_user=_require_user, _ids_visibles=_ids_visibles, _in_filter=_in_filter,
        _ZONA_DEFAULT=_ZONA_DEFAULT, asyncio=asyncio, _sb_diag=_sb_diag,
        _sb_get_paginado=_sb_get_paginado, log=log, datetime=datetime,
        timezone=timezone, _agrega_ventana=_agrega_ventana,
        _VENTANAS_ESTAD=_VENTANAS_ESTAD, _now=_now,
    )
