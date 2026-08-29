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


from routers.whatsapp_number_admin import (
    wa2_numero_verificar_core, wa2_numero_patch_core,
)

@router.get("/numeros/{numero_id}/verificar")
async def wa2_numero_verificar(numero_id: str, request: Request):
    return await wa2_numero_verificar_core(
        numero_id, request,
        _require_user=_require_user, sb_get=sb_get, HTTPException=HTTPException,
        httpx=httpx, GRAPH_API=GRAPH_API, WA2_WEBHOOK_URL=WA2_WEBHOOK_URL,
        sb_patch=sb_patch,
    )



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
    return await wa2_numero_patch_core(
        numero_id, req, request,
        _require_user=_require_user, _ids_visibles=_ids_visibles, _now=_now,
        _normaliza_mx=_normaliza_mx, sb_patch=sb_patch, _in_filter=_in_filter,
    )



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


from routers.whatsapp_test_property import wa2_probar_core, _alta_inmueble_core

@router.post("/probar")
async def wa2_probar(req: ProbarReq, request: Request):
    return await wa2_probar_core(
        req, request,
        _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,
        _entrenamiento_de=_entrenamiento_de, _perfil_agente=_perfil_agente,
        HISTORY_LIMIT=HISTORY_LIMIT, recepcion2_responde=recepcion2_responde,
        _parsear_presupuesto=_parsear_presupuesto, _buscar_inmuebles=_buscar_inmuebles,
        _texto_inmueble=_texto_inmueble,
    )



async def _alta_inmueble(user_id: str, datos: dict, wa_id: str, fotos: list | None = None) -> str | None:
    return await _alta_inmueble_core(
        user_id, datos, wa_id, fotos,
        get_org_context=get_org_context, _normaliza_mx=_normaliza_mx,
        _hora_local=_hora_local, _now=_now, sb_post=sb_post, log=log,
    )



from routers.whatsapp_support_runtime import (
    _entrenamiento_de_core, _generar_ficha_pdf_core, _wa_send_document_link_core,
)

async def _entrenamiento_de(user_id: str, numero_id: str) -> dict:
    return await _entrenamiento_de_core(
        user_id, numero_id, sb_get=sb_get, TRAINING_DEFAULTS=TRAINING_DEFAULTS,
    )







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
    return await _generar_ficha_pdf_core(
        p_ficha, httpx=httpx, BROQUER_API_BASE=BROQUER_API_BASE, log=log,
    )



async def _wa_send_document_link(numero: dict, wa_id: str, url: str, filename: str, caption: str = "") -> str | None:
    return await _wa_send_document_link_core(
        numero, wa_id, url, filename, caption, httpx=httpx, GRAPH_API=GRAPH_API, log=log,
    )



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



from routers.whatsapp_cloud_runtime import (
    _wa_send_text_detallado_core, _wa_send_text_core, _wa_marcar_leido_core,
    _descargar_media_core, _transcribir_audio_core, _describir_imagen_core,
    _wa_send_image_core, _wa_send_document_core,
)

async def _wa_send_text_detallado(numero: dict, wa_id: str, texto: str) -> tuple[str | None, dict | None]:
    return await _wa_send_text_detallado_core(
        numero, wa_id, texto, httpx=httpx, GRAPH_API=GRAPH_API, log=log, _revisar_token=_revisar_token,
    )



async def _wa_send_text(numero: dict, wa_id: str, texto: str) -> str | None:
    return await _wa_send_text_core(
        numero, wa_id, texto, WA_MAX_TEXTO=WA_MAX_TEXTO, _wa_send_text_detallado=_wa_send_text_detallado,
    )



async def _wa_marcar_leido(numero: dict, wamid: str | None, escribiendo: bool = True) -> None:
    return await _wa_marcar_leido_core(
        numero, wamid, escribiendo, httpx=httpx, GRAPH_API=GRAPH_API, log=log,
    )



async def _descargar_media(numero: dict, media_id: str) -> tuple[bytes | None, str]:
    return await _descargar_media_core(
        numero, media_id, httpx=httpx, GRAPH_API=GRAPH_API, log=log,
    )




async def _transcribir_audio(contenido: bytes, mime: str) -> str:
    return await _transcribir_audio_core(
        contenido, mime, GROQ_API_KEY=GROQ_API_KEY, httpx=httpx, GROQ_BASE=GROQ_BASE, log=log,
    )



async def _describir_imagen(contenido: bytes, mime: str) -> str:
    return await _describir_imagen_core(
        contenido, mime, ANTHROPIC_API_KEY=ANTHROPIC_API_KEY, httpx=httpx,
        ANTHROPIC_BASE=ANTHROPIC_BASE, WA2_MODEL=WA2_MODEL, log=log,
    )



async def _wa_send_image(numero: dict, wa_id: str, url: str, caption: str = "") -> str | None:
    return await _wa_send_image_core(
        numero, wa_id, url, caption, httpx=httpx, GRAPH_API=GRAPH_API, log=log,
    )



async def _wa_send_document(numero: dict, wa_id: str, contenido: bytes, filename: str, caption: str) -> None:
    return await _wa_send_document_core(
        numero, wa_id, contenido, filename, caption, httpx=httpx, GRAPH_API=GRAPH_API, log=log,
    )



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


from routers.whatsapp_template_api import (wa2_plantillas_list_core, wa2_plantilla_crear_core, wa2_enviar_plantilla_core)

@router.get("/plantillas")
async def wa2_plantillas_list(request: Request, numero_id: str):
    return await wa2_plantillas_list_core(
        request, numero_id, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,
        httpx=httpx, GRAPH_API=GRAPH_API, log=log,
    )



@router.post("/plantillas")
async def wa2_plantilla_crear(req: PlantillaCrearReq, request: Request):
    return await wa2_plantilla_crear_core(
        req, request, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException, re=re,
        httpx=httpx, GRAPH_API=GRAPH_API, log=log,
    )



class PlantillaEnviarReq(BaseModel):
    conversacion_id: str
    nombre: str
    idioma: str
    variables: list[str] = []


@router.post("/mensajes/plantilla")
async def wa2_enviar_plantilla(req: PlantillaEnviarReq, request: Request):
    return await wa2_enviar_plantilla_core(
        req, request, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,
        httpx=httpx, GRAPH_API=GRAPH_API, log=log, _guardar_mensaje=_guardar_mensaje,
    )



# =============================================================================
# 7) PERFIL DEL AGENTE (nombre público y zona, para que la IA se presente bien)
# =============================================================================
from routers.whatsapp_agent_profile import _perfil_agente



# =============================================================================
# 8) WEBHOOK — recibe TODOS los números conectados a este módulo
# =============================================================================
from routers.whatsapp_webhook_http import wa2_verify_webhook_core, wa2_receive_webhook_core

@router.get("/webhook")
def wa2_verify_webhook(request: Request):
    return wa2_verify_webhook_core(
        request, WA2_VERIFY_TOKEN=WA2_VERIFY_TOKEN, Response=Response,
    )


@router.post("/webhook")
async def wa2_receive_webhook(request: Request, background: BackgroundTasks):
    return await wa2_receive_webhook_core(
        request, background,
        WA2_APP_SECRET=WA2_APP_SECRET, log=log, Response=Response,
        hmac=hmac, hashlib=hashlib, json=json,
        _persistir_entrantes=_persistir_entrantes,
        _procesar_en_segundo_plano=_procesar_en_segundo_plano,
    )


from routers.whatsapp_number_lookup import _get_numero_core

async def _get_numero(phone_number_id: str) -> dict | None:
    return await _get_numero_core(phone_number_id, sb_get=sb_get)



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



from routers.whatsapp_webhook_ingest import _persistir_entrantes_core

async def _persistir_entrantes(payload: dict):
    return await _persistir_entrantes_core(
        payload,
        _get_numero=_get_numero, log=log, _solo_digitos=_solo_digitos,
        sb_get=sb_get, _es_asesor=_es_asesor,
        _get_o_crea_contacto=_get_o_crea_contacto,
        _get_o_crea_conversacion=_get_o_crea_conversacion,
        _guardar_mensaje=_guardar_mensaje, _entrenamiento_de=_entrenamiento_de,
        _pausar_por_respuesta_manual=_pausar_por_respuesta_manual,
        sb_patch=sb_patch, _now=_now, _agenda_upsert=_agenda_upsert,
        datetime=datetime, timezone=timezone, _descargar_media=_descargar_media,
        _transcribir_audio=_transcribir_audio, _describir_imagen=_describir_imagen,
        re=re, _guardar_archivo=_guardar_archivo, _OPT_OUT_PALABRAS=_OPT_OUT_PALABRAS,
        _revisar_token=_revisar_token, enviar_push=enviar_push,
    )



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
