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

import os
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
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY    = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_ANON_KEY

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE    = os.environ.get("ANTHROPIC_BASE", "https://api.anthropic.com/v1")
WA2_MODEL         = os.environ.get("WA2_MODEL", "claude-sonnet-4-6")

GRAPH_API       = "https://graph.facebook.com/v21.0"
META_APP_ID     = os.environ.get("META_APP_ID", "1709238933850389")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
WA2_VERIFY_TOKEN = os.environ.get("WA2_VERIFY_TOKEN", "broquer2_verify")
# Es la MISMA app de Meta que se usa para el OAuth, así que la firma es la
# misma clave secreta. Si alguien no puso WA_APP_SECRET en Railway, caemos
# a META_APP_SECRET en vez de quedarnos sin verificar nada.
WA2_APP_SECRET   = os.environ.get("WA_APP_SECRET", "") or META_APP_SECRET
WA2_REGISTER_PIN = os.environ.get("WA_REGISTER_PIN", "142857")
# URL pública propia de este módulo (para el override_callback_uri al suscribir)
WA2_WEBHOOK_URL  = os.environ.get("WA2_WEBHOOK_URL", "https://api.broquer.app/whatsapp2/webhook")

BROQUER_API_BASE = os.environ.get("BROQUER_API_BASE", "https://api.broquer.app")
HISTORY_LIMIT = 16

# Zona horaria por defecto de todo el módulo. ESTA CONSTANTE FALTABA: el
# endpoint /whatsapp2/estadisticas la usaba sin que existiera en ningún lado,
# así que reventaba con NameError (error 500) en CUALQUIER llamada que no
# mandara ?zona=... — que es exactamente como la llama estadisticas.html.
# Resultado: la pestaña de WhatsApp en Estadísticas nunca funcionó.
_ZONA_DEFAULT = os.environ.get("WA2_ZONA_DEFAULT", "America/Mexico_City")

# Segundos que se espera antes de contestar, para AGRUPAR mensajes seguidos.
# En WhatsApp la gente no escribe un párrafo: escribe "hola", "busco casa",
# "en Altozano" en tres mensajes de tres segundos. Sin esto se disparaban tres
# respuestas de la IA en paralelo —incoherentes entre sí y pagando tres veces—
# y el prospecto veía a un bot atropellado. Con esto, solo el ÚLTIMO mensaje
# del ráfaga contesta, y contesta ya con los tres en el historial.
try:
    WA2_DEBOUNCE = max(0, int(os.environ.get("WA2_DEBOUNCE_SEG", "8")))
except Exception:
    WA2_DEBOUNCE = 8

# WhatsApp corta los mensajes de texto en 4096 caracteres; arriba de eso Meta
# rechaza el envío completo y el prospecto no recibe NADA.
WA_MAX_TEXTO = 4000

# Cajón de Supabase donde viven las fotos, audios y documentos de WhatsApp.
WA_MEDIA_BUCKET = os.environ.get("WA_MEDIA_BUCKET", "wa-media")

# Transcripción de notas de voz (mismo Groq/Whisper que ya usa el resto).
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE    = os.environ.get("GROQ_BASE", "https://api.groq.com/openai/v1")

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
try:
    WA2_TOPE_IA = max(1, int(os.environ.get("WA2_TOPE_IA", "25")))
except Exception:
    WA2_TOPE_IA = 25

router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])

TRAINING_DEFAULTS = {
    "tono": "cálido y profesional",
    "puede": "resolver dudas del inmueble, mandar fotos y precio, y proponer visitas",
    "debe": "preguntar presupuesto, forma de pago y para cuándo busca",
    "no_debe": "inventar direcciones exactas o precios que no existan en el catálogo",
    "especialidad": "",
    # Base de conocimiento del negocio: lo que la IA NO puede adivinar del
    # catálogo (comisiones, si aceptan Infonavit, dónde está la oficina, qué
    # papeles piden para rentar, etc.). Sin esto, ante cualquier pregunta que
    # no sea "muéstrame casas" la IA se queda muda o —peor— inventa.
    "conocimiento": "",
    "objetivo": "calificar al prospecto y agendar una visita",
    "datos_calificar": ["presupuesto", "forma de pago", "para cuándo busca", "zona de interés"],
    "preguntas_extra": [],
    "escalar_palabras": ["quiero hablar con una persona", "hablar con alguien", "es urgente"],
    "horario_activo": False,
    "hora_inicio": "08:00",
    "hora_fin": "21:00",
    "fuera_horario_msg": None,
    "max_mensajes_ia": 0,
    "activo": True,
    "zona_horaria": "America/Mexico_City",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hora_local(zona: str | None = None) -> datetime:
    """Hora de AHORA en la zona del agente (por defecto Ciudad de México).
    México tiene varias zonas horarias reales (Tijuana, Hermosillo, Cancún,
    etc.), así que esto NUNCA debe asumir Ciudad de México para todo mundo."""
    try:
        return datetime.now(ZoneInfo(zona or "America/Mexico_City"))
    except Exception:
        return datetime.now(timezone.utc) + timedelta(hours=-6)


def _fmt_fecha_larga(dt: datetime) -> str:
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month-1]} de {dt.year}, {dt.strftime('%H:%M')}"


def _normaliza_mx(num: str) -> str:
    n = "".join(ch for ch in str(num) if ch.isdigit())
    if n.startswith("521") and len(n) == 13:
        n = "52" + n[3:]
    return n


def _money(n) -> str:
    try:
        return "$" + f"{int(round(float(n))):,}"
    except Exception:
        return str(n) if n else ""


def _parsear_presupuesto(texto: str) -> int | None:
    """Respaldo por si la IA no manda precio_max en 'filtros' aunque el
    prospecto ya haya dado su presupuesto antes (queda guardado en su ficha
    como texto libre, ej. '2 millones', '800 mil', '$1,200,000')."""
    if not texto:
        return None
    t = texto.lower().replace(",", "").replace("$", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(millones|mill?on|mdp|m\b)", t)
    if m:
        return int(float(m.group(1)) * 1_000_000)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(mil|k\b)", t)
    if m:
        return int(float(m.group(1)) * 1_000)
    m = re.search(r"(\d{5,})", t)  # un número ya completo, ej. "1200000"
    if m:
        return int(m.group(1))
    return None


# =============================================================================
# Helpers de Supabase (REST) — con reintento ante timeout/5xx, igual patrón
# probado que el resto del backend, pero self-contained en este archivo.
# =============================================================================
def _sb_headers() -> dict:
    return {"apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json"}


async def sb_get(table: str, params: dict) -> list:
    ultimo = ""
    for intento in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_sb_headers(), params=params)
            if r.status_code < 300:
                data = r.json()
                return data if isinstance(data, list) else ([data] if data else [])
            ultimo = f"{r.status_code}: {r.text[:300]}"
            if r.status_code < 500:
                break
        except Exception as e:
            ultimo = str(e)
    log.error("sb_get %s falló -> %s", table, ultimo)
    return []


async def sb_post(table: str, body: dict, prefer: str = "return=representation") -> list:
    ultimo = ""
    for intento in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                h = _sb_headers(); h["Prefer"] = prefer
                r = await c.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=body)
            if r.status_code < 300:
                try:
                    data = r.json()
                except Exception:
                    data = []
                return data if isinstance(data, list) else ([data] if data else [])
            if r.status_code == 409:
                log.info("sb_post %s: la fila ya existe (409).", table)
                return []
            ultimo = f"{r.status_code}: {r.text[:300]}"
            if r.status_code < 500:
                break
        except Exception as e:
            ultimo = str(e)
    log.error("sb_post %s falló -> %s", table, ultimo)
    return []


async def sb_patch(table: str, params: dict, body: dict) -> list:
    ultimo = ""
    for intento in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                h = _sb_headers(); h["Prefer"] = "return=representation"
                r = await c.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, params=params, json=body)
            if r.status_code < 300:
                try:
                    data = r.json()
                except Exception:
                    data = []
                return data if isinstance(data, list) else ([data] if data else [])
            ultimo = f"{r.status_code}: {r.text[:300]}"
            if r.status_code < 500:
                break
        except Exception as e:
            ultimo = str(e)
    log.error("sb_patch %s falló -> %s", table, ultimo)
    return []


async def sb_delete(table: str, params: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.delete(f"{SUPABASE_URL}/rest/v1/{table}", headers=_sb_headers(), params=params)
        return r.status_code < 300
    except Exception as e:
        log.error("sb_delete %s falló -> %s", table, e)
        return False


async def get_user_id_from_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{SUPABASE_URL}/auth/v1/user",
                            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"})
            if r.status_code == 200:
                return r.json().get("id")
    except Exception:
        pass
    return None


async def _require_user(request: Request) -> str:
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")
    return user_id


async def _ids_visibles(user_id: str) -> list[str]:
    """A qué user_id puede ver este usuario en WhatsApp 2.0.
    Dueño o admin de una organización: él mismo + todo su equipo.
    Agente normal, o alguien sin organización (cuenta personal): solo él mismo.
    Los números y conversaciones se guardan bajo el user_id de quien conectó
    CADA número (cada agente conecta el suyo); esto decide a cuáles de esos
    user_id tiene permiso de asomarse quien pregunta."""
    ctx = await get_org_context(user_id)
    if not ctx or not ctx.get("org_id") or ctx.get("rol_org") not in ("owner", "admin"):
        return [user_id]
    miembros = await sb_get("organizacion_miembros", {
        "org_id": f"eq.{ctx['org_id']}", "select": "user_id"})
    ids = {m["user_id"] for m in miembros if m.get("user_id")}
    ids.add(user_id)
    return list(ids)


def _in_filter(ids: list[str]) -> str:
    return "in.(" + ",".join(ids) + ")"


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


@router.patch("/numeros/{numero_id}")
async def wa2_numero_patch(numero_id: str, req: NumeroPatchReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    body = {"updated_at": _now()}
    if req.alias is not None:
        body["alias"] = req.alias.strip()
    if req.ia_enabled is not None:
        body["ia_enabled"] = req.ia_enabled
    await sb_patch("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids)}, body)
    return {"ok": True}


@router.delete("/numeros/{numero_id}")
async def wa2_numero_delete(numero_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids),
                                        "select": "waba_id,access_token", "limit": "1"})
    if rows and rows[0].get("waba_id") and rows[0].get("access_token"):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                await c.delete(f"{GRAPH_API}/{rows[0]['waba_id']}/subscribed_apps",
                               params={"access_token": rows[0]["access_token"]})
        except Exception:
            pass
    await sb_delete("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids)})
    return {"ok": True}


# =============================================================================
# 2) ENTRENAMIENTO (identidad de la IA, por número o plantilla default)
# =============================================================================
class TrainingReq(BaseModel):
    numero_id: str | None = None
    nombre_ia: str | None = None
    tono: str | None = None
    identidad: str | None = None
    puede: str | None = None
    debe: str | None = None
    no_debe: str | None = None
    especialidad: str | None = None
    conocimiento: str | None = None
    objetivo: str | None = None
    datos_calificar: list[str] = []
    preguntas_extra: list[str] = []
    escalar_palabras: list[str] = []
    horario_activo: bool = False
    hora_inicio: str = "08:00"
    hora_fin: str = "21:00"
    fuera_horario_msg: str | None = None
    max_mensajes_ia: int = 0
    activo: bool = True
    zona_horaria: str = "America/Mexico_City"


@router.get("/entrenamiento")
async def wa2_training_get(request: Request, numero_id: str | None = None):
    user_id = await _require_user(request)
    if numero_id:
        ids = await _ids_visibles(user_id)
        numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids),
                                                    "select": "id", "limit": "1"})
        if not numero_rows:
            raise HTTPException(status_code=404, detail="Número no encontrado")
        rows = await sb_get("wa2_entrenamiento", {"numero_id": f"eq.{numero_id}", "select": "*", "limit": "1"})
    else:
        rows = await sb_get("wa2_entrenamiento", {"user_id": f"eq.{user_id}", "numero_id": "is.null",
                                                  "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    return dict(TRAINING_DEFAULTS, numero_id=numero_id)


@router.put("/entrenamiento")
async def wa2_training_put(req: TrainingReq, request: Request):
    user_id = await _require_user(request)
    fila = req.dict()
    fila["updated_at"] = _now()

    if req.numero_id:
        # El entrenamiento de un número le pertenece a QUIEN CONECTÓ ese número
        # (así lo relee correctamente el webhook), no a quien lo está editando.
        # El dueño/admin puede editar el de su equipo; por eso se busca por el
        # número real y no por el user_id de quien manda la petición.
        ids = await _ids_visibles(user_id)
        numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{req.numero_id}", "user_id": _in_filter(ids),
                                                    "select": "user_id", "limit": "1"})
        if not numero_rows:
            raise HTTPException(status_code=404, detail="Número no encontrado o no tienes permiso sobre él")
        fila["user_id"] = numero_rows[0]["user_id"]
        existing = await sb_get("wa2_entrenamiento", {"numero_id": f"eq.{req.numero_id}", "select": "id", "limit": "1"})
    else:
        fila["user_id"] = user_id
        existing = await sb_get("wa2_entrenamiento", {"user_id": f"eq.{user_id}", "numero_id": "is.null",
                                                      "select": "id", "limit": "1"})

    if existing:
        guardado = await sb_patch("wa2_entrenamiento", {"id": f"eq.{existing[0]['id']}"}, fila)
    else:
        fila["created_at"] = _now()
        guardado = await sb_post("wa2_entrenamiento", fila)
    if not guardado:
        # sb_patch/sb_post ya reintentaron y loguearon el motivo; si aun así no hay
        # fila de vuelta, algo de verdad no se guardó y hay que decirlo, no fingir.
        raise HTTPException(status_code=500,
            detail="No se pudo guardar el entrenamiento. Vuelve a intentar en un momento; "
                   "si sigue sin guardar, es un problema de conexión con la base de datos.")
    return {"ok": True}


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

    fila = {
        "user_id": user_id,
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


def _reglas_para_prompt(e: dict) -> str:
    partes = []
    if e.get("puede"): partes.append(f"Puedes: {e['puede']}.")
    if e.get("debe"): partes.append(f"Debes: {e['debe']}.")
    if e.get("no_debe"): partes.append(f"Nunca: {e['no_debe']}.")
    if e.get("preguntas_extra"):
        preguntas = e["preguntas_extra"] if isinstance(e["preguntas_extra"], list) else []
        if preguntas:
            partes.append("Además pregunta cuando venga al caso: " + "; ".join(preguntas) + ".")
    return " ".join(partes)


def _conocimiento_para_prompt(e: dict) -> str:
    """Bloque de información del negocio que el agente escribió con sus
    palabras. Es la fuente de verdad para todo lo que NO está en el catálogo:
    comisiones, créditos que aceptan, requisitos, ubicación de la oficina,
    formas de pago, política de apartado, etc."""
    txt = (e.get("conocimiento") or "").strip()
    if not txt:
        return ""
    return ("INFORMACIÓN DEL NEGOCIO (fuente de verdad, úsala tal cual y NUNCA la contradigas):\n"
            f"{txt[:6000]}\n")


def _calificacion_para_prompt(e: dict) -> str:
    datos = e.get("datos_calificar") or TRAINING_DEFAULTS["datos_calificar"]
    if isinstance(datos, str):
        datos = [d.strip() for d in datos.split(",") if d.strip()]
    return ", ".join(datos) if datos else "presupuesto, forma de pago y para cuándo busca"


def _en_horario(e: dict) -> bool:
    if not e.get("horario_activo"):
        return True
    try:
        ahora = _hora_local(e.get("zona_horaria")).strftime("%H:%M")
        return e.get("hora_inicio", "08:00") <= ahora <= e.get("hora_fin", "21:00")
    except Exception:
        return True


# =============================================================================
# 3) EL CEREBRO — Anthropic, con JSON estructurado + acciones
# =============================================================================
async def recepcion2_responde(history: list, contexto: str, agente: dict, entren: dict) -> dict:
    quien = agente.get("nombre") or "tu asesor inmobiliario"
    zona = agente.get("zona") or ""
    ubica = f" en {zona}" if zona else ""
    nombre_ia = entren.get("nombre_ia") or "Recepción"
    identidad = entren.get("identidad") or f"Eres '{nombre_ia}', el asistente de WhatsApp de {quien}, asesor inmobiliario{ubica}."
    tono = entren.get("tono") or TRAINING_DEFAULTS["tono"]
    hoy = _fmt_fecha_larga(_hora_local(entren.get("zona_horaria")))

    system = (
        f"{identidad} Hablas en tono {tono}. Español mexicano, mensajes cortos de WhatsApp, sin emojis. "
        f"Atiendes a un prospecto real. Califícalo con calidez y rapidez, sin sonar a robot ni a interrogatorio: "
        f"averigua {_calificacion_para_prompt(entren)}; cuando haga sentido, ofrece agendar una visita con día y hora. "
        f"Hoy es {hoy}, úsalo para entender 'mañana', 'el sábado', etc.\n\n"
        f"Contexto: {contexto}\n"
        f"{_reglas_para_prompt(entren)}\n"
        f"{_conocimiento_para_prompt(entren)}"
        "REGLA DURA: si te preguntan algo que no viene ni en la información del negocio de arriba ni en "
        "el catálogo, NO lo inventes y NO lo supongas. Di con naturalidad que lo confirmas con el asesor "
        "y sigue la conversación. Inventar una comisión, un requisito, una fecha de entrega o una "
        "dirección es el peor error que puedes cometer.\n"
        "Cuando el prospecto pida ver opciones, o cuando ya sepas lo suficiente para mostrarle propiedades, "
        "NO inventes inmuebles ni des direcciones exactas: en 'accion' pide enviarle opciones con los filtros "
        "que tengas (deja en null lo que no sepas) y el sistema le manda propiedades REALES del catálogo del "
        "asesor. En 'reply' avísale en una línea que se las vas a compartir. Usa esto solo cuando de verdad "
        "toque mostrar propiedades; si sigues calificando, deja 'accion' en null.\n"
        "Cuando el prospecto acepte un día y hora concretos para la visita, ponlo en 'accion' como "
        "agendar_visita con fecha (YYYY-MM-DD) y hora (HH:MM 24h); el sistema le manda la invitación y avisa "
        "al asesor. Si no hay día y hora firmes, no lo pongas.\n"
        "Si el prospecto pide explícitamente hablar con una persona, se molesta, o el caso se sale de tus manos, "
        "pon 'accion' como pasar_a_humano con un motivo breve; el sistema apaga la IA de esta conversación y "
        "avisa al asesor de inmediato.\n"
        "NO TODO EL QUE ESCRIBE ES COMPRADOR. Antes de calificar, entiende con quién hablas: hay propietarios "
        "que quieren VENDER o RENTAR su inmueble, y colegas que traen una propiedad. A ésos no les preguntes "
        "presupuesto ni forma de pago — eso es absurdo y se nota. A ellos pídeles los datos del inmueble.\n"
        "Cuando alguien te ofrezca un inmueble (te manda fotos, o te lo describe), junta lo que puedas: tipo, si es venta o renta, precio, colonia, ciudad, recámaras, "
        "baños, estacionamientos, metros de construcción y de terreno. Lo que falte, pregúntalo con naturalidad "
        "y de poquito en poquito, no de golpe. Cuando ya tengas al menos tipo, operación y colonia, ponlo en "
        "'accion' como registrar_inmueble. REGLA DURA DEL REGISTRO: cada dato del inmueble (colonia, ciudad, "
        "precio, medidas, todo) sale ÚNICA Y EXCLUSIVAMENTE de lo que el remitente escribió o de lo que se ve "
        "en sus fotos. NUNCA tomes la ubicación de la zona donde opera el asesor, de su perfil ni de ninguna "
        "otra parte: que el asesor trabaje en una zona no significa que el inmueble esté ahí. Si el remitente "
        "no ha dicho dónde está, pregúntaselo; deja en null lo que no te hayan dicho. Después de registrarlo "
        "NO le prometas publicación, revisión ni plazos: el sistema le contesta lo justo y el asesor decide.\n"
        "Responde ÚNICAMENTE con un JSON válido, sin texto antes ni después, así:\n"
        '{"reply":"mensaje para el prospecto",'
        '"nombre":"el nombre del prospecto ÚNICAMENTE si él mismo lo dijo en el chat (nunca lo inventes ni lo saques de otro lado), o null",'
        '"temperatura":"Caliente|Tibio|Frío",'
        '"score":0-100,"presupuesto":"texto o null","forma_pago":"crédito|contado|por definir",'
        '"busca":"1 frase o null","resumen":"1 frase para el agente","nota":"1 frase para la bitácora o null",'
        '"accion":null}\n'
        "El campo 'accion' es null casi siempre. Para mostrar propiedades: "
        '{"tipo":"enviar_inmuebles","filtros":{"operacion":"venta|renta|null",'
        '"tipo":"casa|departamento|terreno u otro texto, o null",'
        '"colonia":"la colonia o fraccionamiento exacto que mencionó, o null",'
        '"zona_amplia":"el nombre del desarrollo/zona más grande si lo mencionó además de la colonia '
        '(ej. si dice \'El Olivar en Altozano\', colonia=\'El Olivar\' y zona_amplia=\'Altozano\'), o null",'
        '"ciudad":"la ciudad o municipio que mencionó, o null si no la dijo",'
        '"precio_max":numero o null,"recamaras":numero o null}}. '
        "Usa 'ciudad' ÚNICAMENTE si el prospecto la mencionó de forma explícita en ESTA conversación. "
        "NUNCA la asumas ni la infieras de dónde opera el asesor, de su perfil, ni de nada fuera de lo que el "
        "propio prospecto escribió — el catálogo que se consulta ya es solo el inventario de este asesor, así "
        "que buscar nada más por colonia/zona (sin ciudad) es correcto y suficiente cuando el prospecto no dio "
        "una ciudad. Si el prospecto solo dice una colonia o fraccionamiento, deja 'ciudad' en null y busca "
        "igual — no le digas que no hay nada solo porque falta ese dato. Separa colonia y ciudad en sus propios "
        "campos — nunca los mezcles en un solo texto.\n"
        "'precio_max' es OBLIGATORIO si el prospecto mencionó un presupuesto EN CUALQUIER MOMENTO de esta "
        "conversación, aunque el mensaje más reciente solo hable de ubicación — revisa todo el historial, no "
        "nada más el último mensaje. Conviértelo siempre a un número entero de pesos sin signos ni texto "
        "(\"2 millones\"→2000000, \"2.5 mdp\"→2500000, \"800 mil\"→800000, \"$1,200,000\"→1200000). Nunca mandes "
        "propiedades por encima de un presupuesto que ya te dieron, salvo que el prospecto diga explícitamente "
        "que es flexible o que puede subir el monto.\n"
        "Para agendar: "
        '{"tipo":"agendar_visita","fecha":"YYYY-MM-DD","hora":"HH:MM","inmueble":"texto o null"}. '
        "Para pasar a humano: "
        '{"tipo":"pasar_a_humano","motivo":"texto"}\n'
        "Para registrar un inmueble que te ofrecieron: "
        '{"tipo":"registrar_inmueble","datos":{"titulo":"texto o null","tipo":"casa|departamento|terreno|local u otro",'
        '"operacion":"venta|renta","precio":numero o null,"moneda":"MXN","colonia":"texto o null",'
        '"ciudad":"texto o null","calle":"texto o null","recamaras":numero o null,"banos":numero o null,'
        '"estacionamientos":numero o null,"m2_construccion":numero o null,"m2_terreno":numero o null,'
        '"descripcion":"lo que te contaron del inmueble, en tus palabras"}}\n'
        "NUNCA PROMETAS LO QUE NO PUEDES HACER. Tus únicas capacidades reales son: contestar con la "
        "información de arriba, mandar propiedades del catálogo, agendar visitas, registrar un inmueble que te "
        "ofrezcan y pasarle la conversación al asesor. Si te piden cualquier otra cosa —mandar un contrato, "
        "cotizar un crédito, cobrar, hacer un avalúo, apartar— NO digas que la vas a hacer ni que 'ahorita se "
        "la preparo'. Di que se lo comentas al asesor y pon 'accion' como pasar_a_humano. Prometer algo que "
        "nunca llega es peor que decir que no."
    )

    msgs = list(history)
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs:
        msgs = [{"role": "user", "content": "Hola"}]

    # Antes esto NO revisaba el status code de Anthropic. Cuando la API venía
    # saturada (429 / 529, cosa normal y pasajera) o tardaba, se caía directo al
    # respaldo — y el respaldo era un saludo de bienvenida. O sea: al prospecto
    # que llevaba diez mensajes platicando le llegaba de la nada "¡Hola! ¿Me
    # cuentas qué estás buscando?", como si la IA hubiera perdido la memoria.
    # Ahora se reintenta (esos errores casi siempre se arreglan solos en
    # segundos) y el respaldo se adapta a si la charla ya venía empezada.
    ultimo_error = ""
    for intento in (1, 2, 3):
        try:
            async with httpx.AsyncClient(timeout=45) as c:
                r = await c.post(f"{ANTHROPIC_BASE}/messages",
                                 headers={"x-api-key": ANTHROPIC_API_KEY,
                                          "anthropic-version": "2023-06-01",
                                          "Content-Type": "application/json"},
                                 json={"model": WA2_MODEL, "max_tokens": 1600,
                                       "system": system, "messages": msgs})
            if r.status_code in (408, 429, 500, 502, 503, 504, 529):
                ultimo_error = f"{r.status_code}: {r.text[:200]}"
                await asyncio.sleep(2 * intento)
                continue
            if r.status_code >= 400:
                ultimo_error = f"{r.status_code}: {r.text[:200]}"
                break
            data = r.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
            if not text:
                ultimo_error = "respuesta vacía de Anthropic"
                await asyncio.sleep(2 * intento)
                continue
            t = text.replace("```json", "").replace("```", "").strip()
            s, e = t.find("{"), t.rfind("}")
            if s != -1 and e != -1:
                t = t[s:e + 1]
            salida = json.loads(t)
            if isinstance(salida, dict) and (salida.get("reply") or "").strip():
                return salida
            ultimo_error = "la respuesta no traía 'reply'"
        except Exception as e:
            ultimo_error = str(e)[:200]
            await asyncio.sleep(2 * intento)

    log.error("Recepción 2.0: Anthropic no respondió bien tras 3 intentos -> %s", ultimo_error)
    ya_venia_platicando = len([m for m in msgs if m.get("role") == "user"]) > 1
    if ya_venia_platicando:
        # A media conversación NUNCA hay que saludar de nuevo: eso es lo que
        # delata al bot y espanta al prospecto.
        reply = "Dame un momento, por favor."
        resumen = "La IA no pudo responder por una falla técnica; requiere seguimiento del asesor."
    else:
        reply = "¡Hola! Gracias por escribir. ¿Me cuentas qué estás buscando y para cuándo, y con gusto te ayudo?"
        resumen = "Prospecto nuevo, sin calificar aún."
    return {"reply": reply, "temperatura": "Tibio", "score": 50, "presupuesto": None,
            "forma_pago": "por definir", "busca": None, "resumen": resumen,
            "nota": None, "accion": None, "_falla_tecnica": True}


# =============================================================================
# 4) BÚSQUEDA Y ENVÍO DE INMUEBLES (catálogo real del usuario)
# =============================================================================
async def _buscar_inmuebles(user_id: str, filtros: dict, limit: int = 3) -> tuple[list, bool]:
    """Devuelve (propiedades, zona_sin_resultados). zona_sin_resultados es True
    cuando el prospecto pidió una zona concreta y de verdad no hay nada ahí —
    para que el mensaje sea honesto en vez de mandar propiedades de otro lado
    como si fueran lo que se pidió.

    IMPORTANTE sobre precisión: 'ciudad' es un filtro DURO — si el prospecto
    dijo Morelia, jamás se relaja para buscar en otros municipios. 'colonia'
    se intenta primero exacta y, si no hay nada, con el nombre del desarrollo/
    fraccionamiento más amplio (zona_amplia) — pero SIEMPRE dentro de la misma
    ciudad. Nunca se hace un OR suelto de palabras sin relación entre sí: eso
    era lo que antes hacía que 'Morelia' por sí solo trajera cualquier cosa de
    la ciudad, o que una palabra como 'Olivar' apareciera de casualidad en la
    calle de un inmueble de otro municipio.
    """
    sel = ("id,titulo,tipo,operacion,precio,moneda,colonia,ciudad,calle,"
           "num_exterior,recamaras,banos,m2_construccion,fotos,estatus,descripcion")
    # OJO con el estatus: antes esto era `estatus=not.in.(...)` a secas, y en
    # Postgres una comparación contra NULL nunca da verdadero. Es decir, TODA
    # propiedad con el estatus vacío quedaba invisible para la IA — y muchas
    # propiedades importadas o capturadas rápido no traen estatus. El agente
    # tenía inventario y la IA le decía al prospecto que no había nada.
    #
    # 'no_activa' es el estatus de los inmuebles que la propia IA dio de alta
    # con lo que le mandó un tercero por WhatsApp. Esos NUNCA se le ofrecen a
    # un comprador: nadie ha verificado el precio, la titularidad ni que la
    # propiedad exista. Solo salen del cajón cuando el asesor los activa.
    base = {"user_id": f"eq.{user_id}", "select": sel,
            "or": "(estatus.is.null,estatus.not.in.(vendida,rentada,suspendida,no_activa))",
            "order": "updated_at.desc", "limit": str(limit)}
    op = (filtros.get("operacion") or "").strip().lower()
    if op in ("venta", "renta"):
        base["operacion"] = f"eq.{op}"
    tipo = (filtros.get("tipo") or "").strip()
    if tipo:
        base["tipo"] = f"ilike.*{tipo}*"

    ciudad = (filtros.get("ciudad") or "").strip()
    colonia = (filtros.get("colonia") or "").strip()
    zona_amplia = (filtros.get("zona_amplia") or "").strip()

    def _con_precio_recamaras(p: dict) -> dict:
        p = dict(p)
        if filtros.get("precio_max"):
            try:
                p["precio"] = f"lte.{int(filtros['precio_max'])}"
            except Exception:
                pass
        if filtros.get("recamaras"):
            try:
                p["recamaras"] = f"gte.{int(filtros['recamaras'])}"
            except Exception:
                pass
        return p

    if ciudad or colonia or zona_amplia:
        # La ciudad, si se pidió, es OBLIGATORIA en las tres pasadas — nunca
        # se quita, así jamás se ofrece algo de un municipio distinto.
        def _con_ciudad(p: dict) -> dict:
            if ciudad:
                p = dict(p)
                p["ciudad"] = f"ilike.*{ciudad}*"
            return p

        intentos = []
        if colonia:
            intentos.append({"colonia": f"ilike.*{colonia}*"})
        if zona_amplia and zona_amplia.lower() != colonia.lower():
            intentos.append({"colonia": f"ilike.*{zona_amplia}*"})
        if colonia:
            # Por si el nombre del desarrollo está capturado en la calle y no
            # en la colonia (pasa seguido con fraccionamientos nuevos).
            intentos.append({"calle": f"ilike.*{colonia}*"})
        if not intentos and ciudad:
            intentos.append({})  # solo ciudad, sin colonia — caso "casas en Morelia"

        for extra in intentos:
            params = _con_ciudad({**base, **extra})
            rows = await sb_get("propiedades", _con_precio_recamaras(params))
            if rows:
                return rows, False

        # De verdad no hay nada en esa zona/ciudad: se avisa, no se manda otra
        # cosa en su lugar disfrazada de lo que se pidió.
        return [], True

    # Sin zona pedida: aquí sí tiene sentido relajar precio/recámaras si son
    # demasiado estrictos, porque no cambian LO QUE ES la propiedad, solo el
    # rango — y de perdida se le enseña algo parecido a lo que busca.
    rows = await sb_get("propiedades", _con_precio_recamaras(base))
    if not rows and (filtros.get("precio_max") or filtros.get("recamaras")):
        rows = await sb_get("propiedades", base)
    return rows or [], False




def _texto_inmueble(p: dict) -> str:
    direccion = ", ".join(x for x in [p.get("calle"), p.get("colonia"), p.get("ciudad")] if x)
    det = []
    if p.get("recamaras"): det.append(f"{p['recamaras']} rec")
    if p.get("banos"): det.append(f"{p['banos']} baños")
    if p.get("m2_construccion"): det.append(f"{p['m2_construccion']} m2")
    precio = _money(p.get("precio"))
    return (f"*{p.get('titulo') or p.get('tipo') or 'Propiedad'}*\n"
            f"{direccion or 'Ubicación a consultar'}\n"
            f"{' · '.join(det)}\n"
            f"{precio} {p.get('moneda') or 'MXN'}" + (" / mes" if p.get("operacion") == "renta" else ""))


def _fotos_a_imagenes(fotos) -> list:
    out = []
    for f in (fotos or []):
        if isinstance(f, str) and f.strip():
            out.append({"url": f.strip()})
        elif isinstance(f, dict):
            u = f.get("url") or f.get("original")
            if u:
                out.append({"url": u})
    return out


def _propiedad_para_ficha(p: dict) -> dict:
    """Mapea una fila de `propiedades` al formato que espera build_ficha_html
    en main.py (el mismo motor Playwright que usa el módulo de fichas)."""
    op_raw = (p.get("operacion") or "").strip().lower()
    op_type = "rental" if op_raw == "renta" else "sale"
    operations = []
    if p.get("precio"):
        operations.append({"type": op_type, "amount": p.get("precio"), "currency": p.get("moneda") or "MXN"})
    calle = " ".join(filter(None, [str(p.get("calle") or "").strip(), str(p.get("num_exterior") or "").strip()])).strip()
    return {
        "public_id": p.get("id") or "", "id": p.get("id") or "",
        "title": p.get("titulo") or p.get("tipo") or "Propiedad",
        "property_type": p.get("tipo") or "Propiedad",
        "operations": operations,
        "location": {"name": p.get("colonia") or "", "city": p.get("ciudad") or ""},
        "address": calle,
        "bedrooms": p.get("recamaras"), "bathrooms": p.get("banos"),
        "parking_spaces": p.get("estacionamientos"),
        "construction_size": p.get("m2_construccion"), "lot_size": p.get("m2_terreno"),
        "description": p.get("descripcion") or "",
        "property_images": _fotos_a_imagenes(p.get("fotos")),
    }


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
def _fecha_hora_utc_iso(fecha: str, hora: str, zona: str | None = None) -> str | None:
    """Convierte fecha+hora LOCAL del agente (la que entendió el prospecto) a
    un instante UTC real, con 'Z' explícita. CRÍTICO: nunca mandar
    f"{fecha}T{hora}:00" pelón a una columna timestamptz — Postgres lo toma
    como si ya fuera UTC, y la hora se corre (en México, 6h para atrás)."""
    zona = zona or "America/Mexico_City"
    try:
        y, m, d = (int(x) for x in fecha.split("-"))
        hh, mi = (int(x) for x in hora.split(":")[:2])
    except Exception:
        return None
    try:
        local_dt = datetime(y, m, d, hh, mi, tzinfo=ZoneInfo(zona))
    except Exception:
        local_dt = datetime(y, m, d, hh, mi, tzinfo=ZoneInfo("America/Mexico_City"))
    return local_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _construir_ics(fecha: str, hora: str, titulo: str, descripcion: str, zona: str | None = None) -> str:
    zona = zona or "America/Mexico_City"
    try:
        y, m, d = (int(x) for x in fecha.split("-"))
        hh, mi = (int(x) for x in hora.split(":")[:2])
    except Exception:
        ahora = _hora_local(zona)
        y, m, d, hh, mi = ahora.year, ahora.month, ahora.day, ahora.hour, ahora.minute
    # OJO: fecha/hora vienen en la hora LOCAL del agente (la que entendió el
    # prospecto), no en CDMX. Antes esto sumaba 6h fijas asumiendo Ciudad de
    # México, lo cual está mal para Tijuana, Hermosillo, Cancún, etc. — cada
    # una tiene su propio desfase contra UTC (y Tijuana además tiene horario
    # de verano). zoneinfo lo resuelve bien para cualquier zona del país.
    try:
        local_dt = datetime(y, m, d, hh, mi, tzinfo=ZoneInfo(zona))
    except Exception:
        local_dt = datetime(y, m, d, hh, mi, tzinfo=ZoneInfo("America/Mexico_City"))
    inicio = local_dt.astimezone(timezone.utc)
    fin = inicio + timedelta(hours=1)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = f"{stamp}-{y}{m}{d}{hh}{mi}@broquer.app"
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Broquer//WhatsApp2//ES",
        "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
        f"DTSTART:{inicio.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTEND:{fin.strftime('%Y%m%dT%H%M%SZ')}",
        f"SUMMARY:{titulo}", f"DESCRIPTION:{descripcion}",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(lines)


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


async def _guardar_archivo(user_id: str, conversacion_id: str, contenido: bytes,
                           mime: str, sufijo: str) -> tuple[str | None, str | None]:
    """Sube a Supabase el archivo que mandó el prospecto y devuelve
    (url_publica, ruta_interna).

    Hace falta guardarlo porque la liga que da Meta caduca en minutos y además
    exige el token del número: si solo se guardara esa liga, mañana estaría
    muerta y el agente no podría volver a ver la foto que le mandaron.
    La ruta interna se conserva aparte para poder BORRAR el archivo después."""
    if not contenido or not SUPABASE_URL:
        return None, None
    ext = (mime.split("/")[-1] or "bin").split(";")[0][:8] or "bin"
    ruta = f"{user_id}/{conversacion_id}/{int(datetime.now(timezone.utc).timestamp()*1000)}-{sufijo}.{ext}"
    try:
        h = {k: v for k, v in _sb_headers().items() if k != "Content-Type"}
        h["Content-Type"] = mime or "application/octet-stream"
        h["x-upsert"] = "true"
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post(f"{SUPABASE_URL}/storage/v1/object/{WA_MEDIA_BUCKET}/{ruta}",
                             headers=h, content=contenido)
        if r.status_code >= 300:
            log.warning("No se pudo guardar el archivo de WhatsApp: %s %s", r.status_code, r.text[:200])
            return None, None
        return f"{SUPABASE_URL}/storage/v1/object/public/{WA_MEDIA_BUCKET}/{ruta}", ruta
    except Exception as e:
        log.warning("Error guardando archivo de WhatsApp: %s", e)
        return None, None


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
async def _perfil_agente(user_id: str) -> dict:
    nombre, zona = "", ""
    try:
        rows = await sb_get("usuarios", {"id": f"eq.{user_id}",
                                        "select": "nombre_publico,zona_cobertura", "limit": "1"})
        if rows:
            nombre = (rows[0].get("nombre_publico") or "").strip()
            zona = (rows[0].get("zona_cobertura") or "").strip()
    except Exception:
        pass
    return {"nombre": nombre or "tu asesor inmobiliario", "zona": zona}


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


async def _crear_contacto_crm(user_id: str, wa_id: str, nombre: str | None) -> str | None:
    """Crea el Contacto real en el CRM (tabla `contactos`, la misma de
    Contactos/Leads/Estadísticas) para un prospecto nuevo de WhatsApp 2.0.
    Sigue la MISMA convención de id que usa contactos.html ('c_' + timestamp
    en milisegundos), porque esa columna es TEXT, no uuid."""
    contacto_id = f"c_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    telefono = _normaliza_mx(wa_id)
    fila = {
        "id": contacto_id, "user_id": user_id,
        "nombre": (nombre or telefono or "Prospecto de WhatsApp").upper(),
        "telefono": telefono, "wa": telefono,
        "tipo": "comprador", "fuente": "WhatsApp",
        "notas": "Prospecto creado automáticamente por WhatsApp 2.0.",
        "es_potencial": True, "etiquetas": ["WhatsApp 2.0"],
        "operaciones": [],
        "created_at": _now(), "updated_at": _now(),
    }
    creado = await sb_post("contactos", fila)
    if not creado:
        log.error("No se pudo crear el Contacto en el CRM para wa_id=%s (user=%s)", wa_id, user_id)
        return None
    return contacto_id


async def _sincronizar_contacto_crm(user_id: str, contacto_wa2: dict, resultado_ia: dict | None = None) -> None:
    """Mantiene al día el Contacto real del CRM con lo que la IA va calificando:
    - Notas (historial): se le agrega una línea nueva cada vez (no se borra).
    - Descripción privada: es una FOTO del momento — se sobrescribe con lo
      último que se sabe del prospecto (temperatura, score, presupuesto,
      forma de pago, qué busca, resumen). No es historial, es el estado actual.
    Nunca truena el webhook si el CRM no responde — esto es un espejo, no la
    fuente de verdad de WhatsApp 2.0."""
    crm_id = contacto_wa2.get("contacto_crm_id")
    if not crm_id or not resultado_ia:
        return
    try:
        cambios = {"updated_at": _now()}
        busca = (resultado_ia.get("busca") or "").strip().lower()
        if "rent" in busca:
            cambios["tipo"] = "arrendatario"
        elif busca:
            cambios["tipo"] = "comprador"
        nombre_chat_crm = (resultado_ia.get("nombre") or "").strip()
        if nombre_chat_crm:
            cambios["nombre"] = nombre_chat_crm.upper()
        nota = resultado_ia.get("nota") or resultado_ia.get("resumen")
        if nota:
            rows = await sb_get("contactos", {"id": f"eq.{crm_id}", "select": "notas", "limit": "1"})
            previas = (rows[0].get("notas") or "") if rows else ""
            fecha = _hora_local().strftime("%d/%m %H:%M")
            cambios["notas"] = (previas + f"\n[{fecha} · WhatsApp 2.0] {nota}").strip()

        renglones = []
        if contacto_wa2.get("temperatura"): renglones.append(f"Temperatura: {contacto_wa2['temperatura']}")
        if contacto_wa2.get("score") is not None: renglones.append(f"Score: {contacto_wa2['score']}")
        if contacto_wa2.get("presupuesto"): renglones.append(f"Presupuesto: {contacto_wa2['presupuesto']}")
        if contacto_wa2.get("forma_pago"): renglones.append(f"Forma de pago: {contacto_wa2['forma_pago']}")
        if contacto_wa2.get("busca"): renglones.append(f"Busca: {contacto_wa2['busca']}")
        if contacto_wa2.get("resumen"): renglones.append(f"Resumen: {contacto_wa2['resumen']}")
        if renglones:
            cambios["descripcion_privada"] = "\n".join(renglones)

        await sb_patch("contactos", {"id": f"eq.{crm_id}"}, cambios)
    except Exception as e:
        log.warning("No se pudo sincronizar el Contacto %s del CRM: %s", crm_id, e)


def _solo_digitos(t: str) -> str:
    return re.sub(r"\D", "", t or "")


async def _agenda_upsert(user_id: str, numero_id: str, telefono: str,
                         nombre: str | None = None, conocido: bool | None = None) -> None:
    """Agenda del celular del asesor (wa2_agenda): el nombre con el que ÉL tiene
    registrada a cada persona y si ya la conocía de antes de conectar el número.
    Nunca truena el webhook: la agenda es un apoyo, no la fuente de verdad."""
    try:
        rows = await sb_get("wa2_agenda", {"numero_id": f"eq.{numero_id}",
                                           "telefono": f"eq.{telefono}", "select": "*", "limit": "1"})
        if rows:
            cambios = {"updated_at": _now()}
            if nombre:
                cambios["nombre"] = nombre
            if conocido is not None:
                cambios["conocido"] = conocido
            await sb_patch("wa2_agenda", {"id": f"eq.{rows[0]['id']}"}, cambios)
        else:
            await sb_post("wa2_agenda", {"user_id": user_id, "numero_id": numero_id,
                                         "telefono": telefono, "nombre": nombre,
                                         "conocido": bool(conocido),
                                         "created_at": _now(), "updated_at": _now()})
    except Exception as e:
        log.warning("wa2_agenda no se pudo actualizar (%s): %s", telefono, e)


async def _get_o_crea_contacto(user_id: str, numero_id: str, wa_id: str, nombre: str | None) -> dict:
    rows = await sb_get("wa2_contactos", {"numero_id": f"eq.{numero_id}", "wa_id": f"eq.{wa_id}",
                                          "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    # Prioridad de nombre del lead: 1) cómo se presentó él mismo en el chat (lo
    # llena la IA cuando lo diga), 2) cómo lo tiene el asesor en la agenda de su
    # celular, 3) el nombre que el lead se puso en WhatsApp SOLO como último
    # recurso, cuando no existen los otros dos.
    agenda = await sb_get("wa2_agenda", {"numero_id": f"eq.{numero_id}",
                                         "telefono": f"eq.{_solo_digitos(wa_id)}",
                                         "select": "*", "limit": "1"})
    nombre_agenda = (agenda[0].get("nombre") or "").strip() if agenda else ""
    conocido = bool(agenda and agenda[0].get("conocido"))
    display = nombre_agenda or (nombre or "").strip() or None
    contacto_crm_id = await _crear_contacto_crm(user_id, wa_id, display)
    created = await sb_post("wa2_contactos", {
        "user_id": user_id, "numero_id": numero_id, "wa_id": wa_id,
        "nombre": display, "nombre_agenda": nombre_agenda or None,
        "nombre_wa": (nombre or None), "conocido": conocido,
        "contacto_crm_id": contacto_crm_id,
        "created_at": _now(), "updated_at": _now(),
    })
    if created:
        return created[0]
    rows = await sb_get("wa2_contactos", {"numero_id": f"eq.{numero_id}", "wa_id": f"eq.{wa_id}",
                                          "select": "*", "limit": "1"})
    return rows[0] if rows else {}


async def _get_o_crea_conversacion(user_id: str, numero_id: str, contacto_id: str,
                                   ia_default: bool = True) -> dict:
    rows = await sb_get("wa2_conversaciones", {"contacto_id": f"eq.{contacto_id}", "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    # Un CONOCIDO del asesor (agenda del celular o historial previo) arranca con
    # la IA apagada: la recepcionista es para prospectos nuevos, no para caerle
    # en frío a un cliente de años. El asesor la puede prender en esa conversación.
    created = await sb_post("wa2_conversaciones", {
        "user_id": user_id, "numero_id": numero_id, "contacto_id": contacto_id,
        "ai_enabled": ia_default,
        "created_at": _now(), "last_message_at": _now(),
    })
    if created:
        return created[0]
    rows = await sb_get("wa2_conversaciones", {"contacto_id": f"eq.{contacto_id}", "select": "*", "limit": "1"})
    return rows[0] if rows else {}


async def _guardar_mensaje(user_id: str, contacto_id: str, conversacion_id: str, wamid: str | None,
                          direction: str, sender: str, body: str, media_url: str | None = None,
                          media_path: str | None = None) -> None:
    fila = {"user_id": user_id, "contacto_id": contacto_id, "conversacion_id": conversacion_id,
            "direction": direction, "sender": sender, "body": body, "media_url": media_url,
            "media_path": media_path, "created_at": _now()}
    if wamid:
        fila["wa_message_id"] = wamid
    guardado = await sb_post("wa2_mensajes", fila)
    if not guardado and wamid:
        ya = await sb_get("wa2_mensajes", {"wa_message_id": f"eq.{wamid}", "select": "id", "limit": "1"})
        if not ya:
            log.error("wa2_mensajes NO guardado: conv=%s sender=%s", conversacion_id, sender)
    cambios_conv = {"last_message_at": _now()}
    if direction == "in":
        # Esto (no 'last_message_at') es lo que de verdad marca la ventana de
        # 24h de WhatsApp: se cuenta desde el último mensaje del PROSPECTO,
        # no desde el último mensaje de quien sea (agente, IA, prospecto).
        cambios_conv["last_inbound_at"] = _now()
        # Se guarda el id de Meta del último mensaje del prospecto: es lo que
        # se necesita para mandarle la palomita azul cuando el agente abra la
        # conversación en Broquer (no antes).
        if wamid:
            cambios_conv["last_inbound_wamid"] = wamid
    await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"}, cambios_conv)


def _resolver_inmueble_id(inmueble_txt: str, ultimas: list) -> str | None:
    """Si el prospecto ya vio 1 sola propiedad en esta charla, es esa. Si vio
    varias, se intenta encontrar cuál por el texto que puso la IA en 'inmueble'."""
    if not ultimas:
        return None
    if len(ultimas) == 1:
        return ultimas[0].get("id")
    texto = (inmueble_txt or "").strip().lower()
    if not texto:
        return None
    for p in ultimas:
        titulo = (p.get("titulo") or "").strip().lower()
        if titulo and (titulo in texto or texto in titulo):
            return p.get("id")
    return None


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
                contacto_eco = await _get_o_crea_contacto(numero["user_id"], numero["id"], wa_dest, None)
                if not contacto_eco:
                    continue
                conv_eco = await _get_o_crea_conversacion(numero["user_id"], numero["id"],
                                                          contacto_eco["id"], ia_default=False)
                await _guardar_mensaje(numero["user_id"], contacto_eco["id"], conv_eco["id"],
                                      eco.get("id"), "out", "agente", cuerpo)
                if conv_eco.get("ai_enabled", True):
                    await sb_patch("wa2_conversaciones", {"id": f"eq.{conv_eco['id']}"},
                                   {"ai_enabled": False})
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

                contacto = await _get_o_crea_contacto(numero["user_id"], numero["id"], wa_id,
                                                      contactos_meta.get(wa_id))
                conv = await _get_o_crea_conversacion(numero["user_id"], numero["id"], contacto["id"],
                                                     ia_default=not contacto.get("conocido"))

                media_url, media_path = (None, None)
                if media_bytes:
                    media_url, media_path = await _guardar_archivo(
                        numero["user_id"], conv["id"], media_bytes, media_mime, media_sufijo)

                await _guardar_mensaje(numero["user_id"], contacto["id"], conv["id"], msg.get("id"),
                                      "in", "lead", texto, media_url, media_path)
                await sb_patch("wa2_conversaciones", {"id": f"eq.{conv['id']}"},
                              {"unread_count": (conv.get("unread_count") or 0) + 1})

                trabajo.append({"numero": numero, "contacto_id": contacto["id"],
                               "conversacion_id": conv["id"], "wa_id": wa_id, "texto": texto,
                               "wa_message_id": msg.get("id")})

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
    contacto_push = await sb_get("wa2_contactos", {"id": f"eq.{item['contacto_id']}",
                                                   "select": "nombre", "limit": "1"})
    await enviar_push(user_id,
                      (contacto_push[0].get("nombre") if contacto_push else None) or "Nuevo mensaje de WhatsApp",
                      item["texto"], datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})

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
        await _responder_conversacion(item, numero, user_id)


async def _responder_conversacion(item: dict, numero: dict, user_id: str):
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}", "select": "*", "limit": "1"})
    conv = conv_rows[0] if conv_rows else {}
    contacto_rows = await sb_get("wa2_contactos", {"id": f"eq.{item['contacto_id']}", "select": "*", "limit": "1"})
    contacto = contacto_rows[0] if contacto_rows else {}

    # (El aviso al celular ya se mandó en _procesar_en_segundo_plano.)

    if not numero.get("ia_enabled", True) or not conv.get("ai_enabled", True):
        return  # el humano tiene el control

    entren = await _entrenamiento_de(user_id, numero["id"])
    if not entren.get("activo", True):
        return
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
        await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"}, {"ai_enabled": False})
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
        await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"}, {"ai_enabled": False})
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
        await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"}, {"ai_enabled": False})
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
                               {"ai_enabled": False})
                await enviar_push(user_id, "No se pudo guardar un inmueble",
                                  f"{contacto.get('nombre') or item['wa_id']} te mandó una propiedad y "
                                  "no se pudo registrar. Entra a la conversación.",
                                  datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})

        elif tipo == "pasar_a_humano":
            await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"}, {"ai_enabled": False})
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
    # lado en ESA conversación. Si no, pasa lo más ridículo que puede pasar:
    # el prospecto contesta y le responden dos "personas" distintas, con
    # criterios distintos, en el mismo chat. Se reactiva con el switch de IA.
    ia_pausada = False
    if conv.get("ai_enabled", True):
        await sb_patch("wa2_conversaciones", {"id": f"eq.{conv['id']}"}, {"ai_enabled": False})
        ia_pausada = True
    return {"ok": True, "ia_pausada": ia_pausada}


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
    etapa: str | None = None


@router.patch("/conversaciones/{conversacion_id}")
async def wa2_conversacion_patch(conversacion_id: str, req: ConvPatchReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{conversacion_id}", "user_id": _in_filter(ids),
                                                    "select": "contacto_id", "limit": "1"})
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    if req.ai_enabled is not None:
        await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"}, {"ai_enabled": req.ai_enabled})
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
    await sb_delete("wa2_conversaciones", {"id": f"eq.{conversacion_id}"})
    if conv[0].get("contacto_id"):
        await sb_delete("wa2_contactos", {"id": f"eq.{conv[0]['contacto_id']}"})
    log.info("Conversación %s eliminada por el usuario %s", conversacion_id, user_id)
    return {"ok": True}


async def _borrar_archivos(rutas: list) -> None:
    """Borra del almacenamiento los archivos de los mensajes que se eliminan.
    Si esto no se hiciera, la foto seguiría viva en una liga pública aunque el
    mensaje ya no apareciera en ningún lado — que es justo lo contrario de lo
    que promete una supresión."""
    rutas = [r for r in (rutas or []) if r]
    if not rutas:
        return
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            await c.request("DELETE", f"{SUPABASE_URL}/storage/v1/object/{WA_MEDIA_BUCKET}",
                            headers=_sb_headers(), json={"prefixes": rutas})
    except Exception as e:
        log.warning("No se pudieron borrar %s archivo(s) del almacenamiento: %s", len(rutas), e)


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
                if k in ("nombre", "presupuesto", "forma_pago", "busca", "temperatura", "score", "etapa", "resumen")}
    await sb_patch("wa2_contactos", {"id": f"eq.{contacto_id}", "user_id": _in_filter(ids)}, permitido)
    return {"ok": True}


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
    """Igual que sb_get pero DEVUELVE el error en vez de tragárselo.
    sb_get regresa [] tanto si no hay filas como si la consulta falló: para
    estadísticas eso es fatal, porque una columna que no existe se veía
    exactamente igual que 'no tienes datos'."""
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_sb_headers(), params=params)
        if r.status_code < 300:
            data = r.json()
            return (data if isinstance(data, list) else ([data] if data else [])), ""
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


def _dt(valor) -> datetime | None:
    """Parsea un timestamptz de Postgres a datetime con zona. Nunca revienta."""
    if not valor:
        return None
    try:
        txt = str(valor).replace("Z", "+00:00")
        d = datetime.fromisoformat(txt)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _mediana(nums: list) -> float | None:
    if not nums:
        return None
    s = sorted(nums)
    n = len(s)
    medio = n // 2
    return float(s[medio]) if n % 2 else (s[medio - 1] + s[medio]) / 2.0


def _agrega_ventana(dias: int, ahora_utc: datetime, zona: str,
                    contactos: list, conversaciones: list, mensajes: list,
                    numeros: list) -> dict:
    """Todos los números de WhatsApp para una ventana de tiempo."""
    try:
        tz = ZoneInfo(zona)
    except Exception:
        tz = timezone.utc
    corte = ahora_utc - timedelta(days=dias) if dias else None

    def dentro(d: datetime | None) -> bool:
        if corte is None:
            return d is not None
        return d is not None and d >= corte

    # ── Mensajes ────────────────────────────────────────────────────────
    serie: dict = {}                 # fecha local -> {entrantes, ia, agente}
    heat = [[0] * 24 for _ in range(7)]   # [día de semana][hora] de entrantes
    tot = {"mensajes": 0, "entrantes": 0, "salientes": 0, "ia": 0, "agente": 0}
    por_conv: dict = {}
    for m in mensajes:
        d = _dt(m.get("created_at"))
        if not dentro(d):
            continue
        local = d.astimezone(tz)
        clave = local.date().isoformat()
        fila = serie.setdefault(clave, {"entrantes": 0, "ia": 0, "agente": 0})
        entrante = (m.get("direction") or "") == "in"
        sender = (m.get("sender") or "").lower()
        tot["mensajes"] += 1
        if entrante:
            tot["entrantes"] += 1
            fila["entrantes"] += 1
            heat[local.weekday()][local.hour] += 1
        else:
            tot["salientes"] += 1
            if sender == "ia":
                tot["ia"] += 1
                fila["ia"] += 1
            else:
                tot["agente"] += 1
                fila["agente"] += 1
        cid = m.get("conversacion_id")
        if cid:
            por_conv.setdefault(cid, []).append((d, entrante, sender))

    # ── Tiempo de primera respuesta (minutos) ───────────────────────────
    resp_todas, resp_ia, resp_agente, sin_responder = [], [], [], 0
    for cid, filas in por_conv.items():
        filas.sort(key=lambda x: x[0])
        if filas and filas[-1][1]:
            sin_responder += 1
        esperando = None
        for fecha, entrante, sender in filas:
            if entrante:
                if esperando is None:
                    esperando = fecha
            elif esperando is not None:
                minutos = max(0.0, (fecha - esperando).total_seconds() / 60.0)
                if minutos <= 60 * 72:      # más de 3 días ya no es "respuesta"
                    resp_todas.append(minutos)
                    (resp_ia if sender == "ia" else resp_agente).append(minutos)
                esperando = None

    # ── Contactos (calificación de la IA) ───────────────────────────────
    temperatura: dict = {}
    etapa: dict = {}
    forma_pago: dict = {}
    scores: list = []
    score_buckets = {"0-24": 0, "25-49": 0, "50-74": 0, "75-100": 0}
    contactos_nuevos = 0
    for c in contactos:
        if dentro(_dt(c.get("created_at"))):
            contactos_nuevos += 1
        # el estado de calificación es SIEMPRE el de hoy, no el del periodo:
        # un prospecto caliente lo es ahora, no "la semana pasada".
        t = (c.get("temperatura") or "Nuevo").strip() or "Nuevo"
        temperatura[t] = temperatura.get(t, 0) + 1
        e = (c.get("etapa") or "Nuevo").strip() or "Nuevo"
        etapa[e] = etapa.get(e, 0) + 1
        fp = (c.get("forma_pago") or "Por definir").strip() or "Por definir"
        forma_pago[fp] = forma_pago.get(fp, 0) + 1
        sc = c.get("score")
        if isinstance(sc, (int, float)):
            scores.append(float(sc))
            if sc < 25:
                score_buckets["0-24"] += 1
            elif sc < 50:
                score_buckets["25-49"] += 1
            elif sc < 75:
                score_buckets["50-74"] += 1
            else:
                score_buckets["75-100"] += 1

    # ── Conversaciones ──────────────────────────────────────────────────
    convs_nuevas = 0
    convs_activas = 0
    handoffs = 0
    propiedades: dict = {}
    por_numero: dict = {}
    dia_24h = ahora_utc - timedelta(hours=24)
    for cv in conversaciones:
        creada = _dt(cv.get("created_at"))
        ultimo = _dt(cv.get("last_message_at"))
        nueva = dentro(creada)
        movida = dentro(ultimo)
        if nueva:
            convs_nuevas += 1
        if ultimo and ultimo >= dia_24h:
            convs_activas += 1
        if movida and cv.get("ia_enabled") is False:
            handoffs += 1
        if movida:
            for p in (cv.get("ultimas_propiedades") or []):
                pid = p.get("id") if isinstance(p, dict) else p
                if not pid:
                    continue
                reg = propiedades.setdefault(str(pid), {"conversaciones": 0, "titulo": None})
                reg["conversaciones"] += 1
                if isinstance(p, dict) and p.get("titulo"):
                    reg["titulo"] = p.get("titulo")
        nid = cv.get("numero_id")
        if nid:
            reg = por_numero.setdefault(str(nid), {"conversaciones": 0, "nuevas": 0})
            if movida:
                reg["conversaciones"] += 1
            if nueva:
                reg["nuevas"] += 1

    # mensajes por número (vía conversación)
    conv_numero = {str(cv.get("id")): str(cv.get("numero_id") or "") for cv in conversaciones}
    msg_numero: dict = {}
    for cid, filas in por_conv.items():
        nid = conv_numero.get(str(cid))
        if not nid:
            continue
        reg = msg_numero.setdefault(nid, {"mensajes": 0, "entrantes": 0, "ia": 0})
        for _f, entrante, sender in filas:
            reg["mensajes"] += 1
            if entrante:
                reg["entrantes"] += 1
            elif sender == "ia":
                reg["ia"] += 1

    numeros_out = []
    for n in numeros:
        nid = str(n.get("id"))
        a = por_numero.get(nid, {"conversaciones": 0, "nuevas": 0})
        b = msg_numero.get(nid, {"mensajes": 0, "entrantes": 0, "ia": 0})
        salientes_n = b["mensajes"] - b["entrantes"]
        numeros_out.append({
            "id": nid,
            "alias": n.get("alias") or n.get("display_number") or "Número",
            "display_number": n.get("display_number"),
            "ia_enabled": n.get("ia_enabled") is not False,
            "conversaciones": a["conversaciones"],
            "nuevas": a["nuevas"],
            "mensajes": b["mensajes"],
            "entrantes": b["entrantes"],
            "pct_ia": round((b["ia"] / salientes_n) * 100) if salientes_n else 0,
        })
    numeros_out.sort(key=lambda x: x["mensajes"], reverse=True)

    salientes = tot["salientes"]
    return {
        "totales": {
            **tot,
            "conversaciones_nuevas": convs_nuevas,
            "conversaciones_activas_24h": convs_activas,
            "contactos_nuevos": contactos_nuevos,
            "handoffs": handoffs,
            "sin_responder": sin_responder,
            "pct_ia": round((tot["ia"] / salientes) * 100) if salientes else 0,
            "msgs_por_conversacion": round(tot["mensajes"] / len(por_conv), 1) if por_conv else 0,
        },
        "serie": [{"fecha": k, **v} for k, v in sorted(serie.items())],
        "heat": heat,
        "temperatura": temperatura,
        "etapa": etapa,
        "forma_pago": forma_pago,
        "score": {
            "promedio": round(sum(scores) / len(scores)) if scores else None,
            "buckets": score_buckets,
        },
        "respuesta_min": {
            "mediana": round(_mediana(resp_todas), 1) if resp_todas else None,
            "mediana_ia": round(_mediana(resp_ia), 1) if resp_ia else None,
            "mediana_agente": round(_mediana(resp_agente), 1) if resp_agente else None,
            "n": len(resp_todas),
        },
        "numeros": numeros_out,
        "propiedades": propiedades,
    }


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
