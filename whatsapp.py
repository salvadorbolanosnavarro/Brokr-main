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
WA2_APP_SECRET   = os.environ.get("WA_APP_SECRET", "")  # misma app de Meta, misma firma
WA2_REGISTER_PIN = os.environ.get("WA_REGISTER_PIN", "142857")
# URL pública propia de este módulo (para el override_callback_uri al suscribir)
WA2_WEBHOOK_URL  = os.environ.get("WA2_WEBHOOK_URL", "https://api.broquer.app/whatsapp2/webhook")

BROQUER_API_BASE = os.environ.get("BROQUER_API_BASE", "https://api.broquer.app")
HISTORY_LIMIT = 16
router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])

TRAINING_DEFAULTS = {
    "tono": "cálido y profesional",
    "puede": "resolver dudas del inmueble, mandar fotos y precio, y proponer visitas",
    "debe": "preguntar presupuesto, forma de pago y para cuándo busca",
    "no_debe": "inventar direcciones exactas o precios que no existan en el catálogo",
    "especialidad": "",
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
        "Responde ÚNICAMENTE con un JSON válido, sin texto antes ni después, así:\n"
        '{"reply":"mensaje para el prospecto","temperatura":"Caliente|Tibio|Frío",'
        '"score":0-100,"presupuesto":"texto o null","forma_pago":"crédito|contado|por definir",'
        '"busca":"1 frase o null","resumen":"1 frase para el agente","nota":"1 frase para la bitácora o null",'
        '"accion":null}\n'
        "El campo 'accion' es null casi siempre. Para mostrar propiedades: "
        '{"tipo":"enviar_inmuebles","filtros":{"operacion":"venta|renta|null",'
        '"tipo":"casa|departamento|terreno u otro texto, o null","zona":"colonia o ciudad, o null",'
        '"precio_max":numero o null,"recamaras":numero o null}}. '
        "Para agendar: "
        '{"tipo":"agendar_visita","fecha":"YYYY-MM-DD","hora":"HH:MM","inmueble":"texto o null"}. '
        "Para pasar a humano: "
        '{"tipo":"pasar_a_humano","motivo":"texto"}'
    )

    msgs = list(history)
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs:
        msgs = [{"role": "user", "content": "Hola"}]

    try:
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post(f"{ANTHROPIC_BASE}/messages",
                             headers={"x-api-key": ANTHROPIC_API_KEY,
                                      "anthropic-version": "2023-06-01",
                                      "Content-Type": "application/json"},
                             json={"model": WA2_MODEL, "max_tokens": 700, "system": system, "messages": msgs})
            data = r.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
            if not text:
                raise ValueError("respuesta vacía de Anthropic")
            t = text.replace("```json", "").replace("```", "").strip()
            s, e = t.find("{"), t.rfind("}")
            if s != -1 and e != -1:
                t = t[s:e + 1]
            return json.loads(t)
    except Exception as e:
        log.exception("Error en Recepción 2.0 (Anthropic): %s", e)
        return {"reply": "¡Hola! Gracias por escribir. ¿Me cuentas qué estás buscando y para cuándo, y con gusto te ayudo?",
                "temperatura": "Tibio", "score": 50, "presupuesto": None, "forma_pago": "por definir",
                "busca": None, "resumen": "Prospecto nuevo, sin calificar aún.", "nota": None, "accion": None}


# =============================================================================
# 4) BÚSQUEDA Y ENVÍO DE INMUEBLES (catálogo real del usuario)
# =============================================================================
async def _buscar_inmuebles(user_id: str, filtros: dict, limit: int = 3) -> tuple[list, bool]:
    """Devuelve (propiedades, zona_sin_resultados). zona_sin_resultados es True
    cuando el prospecto pidió una zona concreta y de verdad no hay nada ahí —
    para que el mensaje sea honesto en vez de mandar propiedades de otro lado
    como si fueran lo que se pidió."""
    sel = ("id,titulo,tipo,operacion,precio,moneda,colonia,ciudad,calle,"
           "num_exterior,recamaras,banos,m2_construccion,fotos,estatus")
    # OJO: los valores reales de "estatus" en Broquer son activa/reservada/
    # en_proceso/vendida/rentada/suspendida (ver propiedades.html) — "publicada"
    # nunca existe, así que filtrar por eso dejaba la búsqueda siempre vacía.
    # Lo correcto es EXCLUIR lo que de plano ya no se puede ofrecer.
    base = {"user_id": f"eq.{user_id}", "select": sel,
            "estatus": "not.in.(vendida,rentada,suspendida)",
            "order": "updated_at.desc", "limit": str(limit)}
    op = (filtros.get("operacion") or "").strip().lower()
    if op in ("venta", "renta"):
        base["operacion"] = f"eq.{op}"
    tipo = (filtros.get("tipo") or "").strip()
    if tipo:
        base["tipo"] = f"ilike.*{tipo}*"
    zona = (filtros.get("zona") or "").strip()

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

    if zona:
        zona_limpia = zona.replace(",", " ")
        exacta = dict(base)
        exacta["or"] = f"(colonia.ilike.*{zona_limpia}*,ciudad.ilike.*{zona_limpia}*,calle.ilike.*{zona_limpia}*)"
        rows = await sb_get("propiedades", _con_precio_recamaras(exacta))
        if rows:
            return rows, False

        # La colonia puede venir mal escrita o con solo parte del nombre real
        # ("Tres Marías" vs "Álamos Tres Marías 3ra Sección"): se intenta
        # palabra por palabra, siempre dentro de la MISMA zona, nunca fuera.
        palabras = [w for w in re.split(r"\s+", zona_limpia) if len(w) >= 4]
        if palabras:
            ors = ",".join(f"colonia.ilike.*{w}*,ciudad.ilike.*{w}*,calle.ilike.*{w}*" for w in palabras)
            relajada = dict(base)
            relajada["or"] = f"({ors})"
            rows = await sb_get("propiedades", _con_precio_recamaras(relajada))
            if rows:
                return rows, False

        # De verdad no hay nada en esa zona: se avisa, no se manda otra cosa
        # en su lugar disfrazada de lo que se pidió.
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
            return None, {"code": err.get("code"), "message": err.get("message") or "No se pudo enviar el mensaje."}
        d = r.json()
        msgs = d.get("messages") or []
        return (msgs[0].get("id") if msgs else None), None


async def _wa_send_text(numero: dict, wa_id: str, texto: str) -> str | None:
    wamid, _ = await _wa_send_text_detallado(numero, wa_id, texto)
    return wamid


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

    if WA2_APP_SECRET:
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


async def _get_o_crea_contacto(user_id: str, numero_id: str, wa_id: str, nombre: str | None) -> dict:
    rows = await sb_get("wa2_contactos", {"numero_id": f"eq.{numero_id}", "wa_id": f"eq.{wa_id}",
                                          "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    contacto_crm_id = await _crear_contacto_crm(user_id, wa_id, nombre)
    created = await sb_post("wa2_contactos", {
        "user_id": user_id, "numero_id": numero_id, "wa_id": wa_id,
        "nombre": nombre, "contacto_crm_id": contacto_crm_id,
        "created_at": _now(), "updated_at": _now(),
    })
    if created:
        return created[0]
    rows = await sb_get("wa2_contactos", {"numero_id": f"eq.{numero_id}", "wa_id": f"eq.{wa_id}",
                                          "select": "*", "limit": "1"})
    return rows[0] if rows else {}


async def _get_o_crea_conversacion(user_id: str, numero_id: str, contacto_id: str) -> dict:
    rows = await sb_get("wa2_conversaciones", {"contacto_id": f"eq.{contacto_id}", "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    created = await sb_post("wa2_conversaciones", {
        "user_id": user_id, "numero_id": numero_id, "contacto_id": contacto_id,
        "created_at": _now(), "last_message_at": _now(),
    })
    if created:
        return created[0]
    rows = await sb_get("wa2_conversaciones", {"contacto_id": f"eq.{contacto_id}", "select": "*", "limit": "1"})
    return rows[0] if rows else {}


async def _guardar_mensaje(user_id: str, contacto_id: str, conversacion_id: str, wamid: str | None,
                          direction: str, sender: str, body: str, media_url: str | None = None) -> None:
    fila = {"user_id": user_id, "contacto_id": contacto_id, "conversacion_id": conversacion_id,
            "direction": direction, "sender": sender, "body": body, "media_url": media_url,
            "created_at": _now()}
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
    await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"}, cambios_conv)


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

                texto = ""
                if msg.get("type") == "text":
                    texto = (msg.get("text") or {}).get("body", "")
                elif msg.get("type") in ("image", "document", "audio", "video"):
                    texto = f"[{msg['type']}]"
                else:
                    texto = "[mensaje no soportado]"

                existe = await sb_get("wa2_mensajes", {"wa_message_id": f"eq.{msg.get('id')}",
                                                       "select": "id", "limit": "1"})
                if existe:
                    continue

                contacto = await _get_o_crea_contacto(numero["user_id"], numero["id"], wa_id,
                                                      contactos_meta.get(wa_id))
                conv = await _get_o_crea_conversacion(numero["user_id"], numero["id"], contacto["id"])
                await _guardar_mensaje(numero["user_id"], contacto["id"], conv["id"], msg.get("id"),
                                      "in", "lead", texto)
                await sb_patch("wa2_conversaciones", {"id": f"eq.{conv['id']}"},
                              {"unread_count": (conv.get("unread_count") or 0) + 1})

                trabajo.append({"numero": numero, "contacto_id": contacto["id"],
                               "conversacion_id": conv["id"], "wa_id": wa_id, "texto": texto})
    return True, trabajo


async def _procesar_en_segundo_plano(item: dict):
    numero = item["numero"]
    user_id = numero["user_id"]
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}", "select": "*", "limit": "1"})
    conv = conv_rows[0] if conv_rows else {}
    contacto_rows = await sb_get("wa2_contactos", {"id": f"eq.{item['contacto_id']}", "select": "*", "limit": "1"})
    contacto = contacto_rows[0] if contacto_rows else {}

    # Notifica siempre que llega un mensaje nuevo
    await enviar_push(user_id, contacto.get("nombre") or "Nuevo mensaje (WhatsApp 2.0)",
                      item["texto"], datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})

    if not numero.get("ia_enabled", True) or not conv.get("ai_enabled", True):
        return  # el humano tiene el control

    entren = await _entrenamiento_de(user_id, numero["id"])
    if not entren.get("activo", True):
        return
    if not _en_horario(entren):
        msg_fuera = entren.get("fuera_horario_msg") or "Gracias por tu mensaje, en cuanto abramos te contesto."
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

    max_msj = entren.get("max_mensajes_ia") or 0
    if max_msj:
        conteo = await sb_get("wa2_mensajes", {"conversacion_id": f"eq.{item['conversacion_id']}",
                                               "sender": "eq.ia", "select": "id"})
        if len(conteo) >= max_msj:
            await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"}, {"ai_enabled": False})
            return

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

    # Actualiza la ficha del prospecto con lo que la IA acaba de calificar
    notas_actuales = contacto.get("notas") or []
    if resultado.get("nota"):
        notas_actuales = notas_actuales + [{"texto": resultado["nota"], "autor": "ia", "fecha": _now()}]
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
    await sb_patch("wa2_contactos", {"id": f"eq.{item['contacto_id']}"}, update_contacto)
    await _sincronizar_contacto_crm(user_id, dict(contacto, **update_contacto), resultado)

    accion = resultado.get("accion")
    if isinstance(accion, dict):
        tipo = accion.get("tipo")
        if tipo == "enviar_inmuebles":
            filtros_ia = accion.get("filtros") or {}
            props, zona_sin_resultados = await _buscar_inmuebles(user_id, filtros_ia)
            if props:
                for p in props[:3]:
                    fotos = p.get("fotos") or []
                    caption = _texto_inmueble(p)
                    if fotos:
                        wamid2 = await _wa_send_image(numero, item["wa_id"], fotos[0], caption)
                    else:
                        wamid2 = await _wa_send_text(numero, item["wa_id"], caption)
                    await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid2,
                                          "out", "ia", caption, fotos[0] if fotos else None)
                    # Ficha técnica completa (PDF con todas las fotos y datos):
                    # mismo motor que usa el módulo de Ficha técnica, solo por HTTP.
                    url_pdf, filename = await _generar_ficha_pdf(_propiedad_para_ficha(p))
                    if url_pdf:
                        wamid3 = await _wa_send_document_link(
                            numero, item["wa_id"], url_pdf, filename or "ficha.pdf",
                            f"Ficha técnica: {p.get('titulo') or p.get('tipo') or 'propiedad'}")
                        await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid3,
                                              "out", "ia", f"[ficha técnica adjunta] {filename}", url_pdf)
            elif zona_sin_resultados:
                # De verdad no hay nada en la zona que pidió: se le dice tal
                # cual, NUNCA se le manda una propiedad de otra ubicación
                # como si fuera lo que preguntó.
                zona_txt = (filtros_ia.get("zona") or "esa zona").strip()
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
                creada = await sb_post("tareas", {
                    "user_id": user_id, "titulo": titulo,
                    "fecha_entrega": _fecha_hora_utc_iso(fecha, hora, entren.get("zona_horaria")),
                    "notas": inmueble_txt or None,
                    "contacto_id": crm_id})
                if creada and crm_id:
                    await sb_post("tareas_contactos", {
                        "user_id": user_id, "tarea_id": creada[0]["id"], "contacto_id": crm_id})
                await sb_patch("wa2_contactos", {"id": f"eq.{item['contacto_id']}"}, {"etapa": "Cita"})
                ics = _construir_ics(fecha, hora, titulo, inmueble_txt, entren.get("zona_horaria"))
                await _wa_send_document(numero, item["wa_id"], ics.encode("utf-8"),
                                       "cita.ics", "Toca el archivo para agregarla a tu calendario.")
                await enviar_push(user_id, "Nueva cita agendada",
                                  f"{nombre_prospecto} — {fecha} {hora} (revísala en Tareas)",
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
    return {"conversaciones": rows}


@router.get("/mensajes")
async def wa2_mensajes_list(request: Request, conversacion_id: str):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_mensajes", {"conversacion_id": f"eq.{conversacion_id}", "user_id": _in_filter(ids),
                                         "select": "*", "order": "created_at.asc", "limit": "300"})
    await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}", "user_id": _in_filter(ids)},
                  {"unread_count": 0})
    return {"mensajes": rows}


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

    wamid, error = await _wa_send_text_detallado(numero, contacto.get("wa_id"), req.texto)
    if error:
        if error.get("code") == 131047:
            raise HTTPException(status_code=409, detail={
                "ventana_cerrada": True,
                "mensaje": "Pasaron más de 24 horas desde el último mensaje del prospecto. "
                           "WhatsApp ya no deja mandar texto libre — usa una plantilla para reabrir la conversación.",
            })
        raise HTTPException(status_code=502, detail=error.get("message") or "No se pudo enviar el mensaje.")
    await _guardar_mensaje(conv["user_id"], conv["contacto_id"], conv["id"], wamid, "out", "agente", req.texto)
    return {"ok": True}


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
