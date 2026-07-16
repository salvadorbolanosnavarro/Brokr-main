# =============================================================================
# Broquer · Módulo WhatsApp (Recepción) — versión amarrada a TU stack
# -----------------------------------------------------------------------------
# Hecho con tus mismos patrones de main.py:
#   - httpx (async) para todo  ->  CERO dependencias nuevas
#   - Supabase por REST directo (apikey + service key), igual que tus helpers
#   - El cerebro corre en Anthropic (claude-sonnet-4-6), tu misma llamada
#   - Reusa el patrón de get_user_id_from_token para la bandeja
#
# Conectar en main.py:
#   from whatsapp import router as whatsapp_router
#   app.include_router(whatsapp_router)
#
# Webhook:  https://TU-APP.railway.app/whatsapp/webhook
# =============================================================================

import os
import json
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException
from pydantic import BaseModel

log = logging.getLogger("broquer.whatsapp")

# -----------------------------------------------------------------------------
# CONFIG  (tus mismos nombres de variables de entorno)
# -----------------------------------------------------------------------------
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY    = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_ANON_KEY

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE    = os.environ.get("ANTHROPIC_BASE", "https://api.anthropic.com/v1")
RECEPCION_MODEL   = os.environ.get("RECEPCION_MODEL", "claude-sonnet-4-6")

GRAPH_API        = "https://graph.facebook.com/v21.0"
WHATSAPP_TOKEN   = os.environ.get("WHATSAPP_TOKEN", "")
WA_VERIFY_TOKEN  = os.environ.get("WA_VERIFY_TOKEN", "broquer_verify")
WA_APP_SECRET    = os.environ.get("WA_APP_SECRET", "")
WA_REGISTER_PIN  = os.environ.get("WA_REGISTER_PIN", "142857")  # PIN de 6 dígitos para 2FA del número

# Piloto (Grupo Navarro): si un número no está mapeado en wa_numbers, usamos esto
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "")
DEFAULT_AGENCIA = os.environ.get("DEFAULT_AGENCIA", "Grupo Navarro")

HISTORY_LIMIT = 14
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Helpers de Supabase (REST, con tu mismo patrón de headers)
# =============================================================================
def _sb_headers() -> dict:
    return {"apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json"}


async def sb_get(table: str, params: dict) -> list:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_sb_headers(), params=params)
        return r.json() if r.status_code < 300 else []


async def sb_post(table: str, body: dict, prefer: str = "return=representation") -> list:
    async with httpx.AsyncClient(timeout=15) as c:
        h = _sb_headers(); h["Prefer"] = prefer
        r = await c.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=body)
        try:
            return r.json()
        except Exception:
            return []


async def sb_patch(table: str, params: dict, body: dict) -> list:
    async with httpx.AsyncClient(timeout=15) as c:
        h = _sb_headers(); h["Prefer"] = "return=representation"
        r = await c.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, params=params, json=body)
        try:
            return r.json()
        except Exception:
            return []


# Igual que tu helper en main.py: saca el user_id del token de Supabase
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


# =============================================================================
# 1) WEBHOOK
# =============================================================================
@router.get("/webhook")
def verify_webhook(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == WA_VERIFY_TOKEN:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    return Response(content="forbidden", status_code=403)


@router.post("/webhook")
async def receive_webhook(request: Request, background: BackgroundTasks):
    raw = await request.body()

    if WA_APP_SECRET:
        import hmac, hashlib
        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(WA_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            log.warning("Firma de webhook inválida")
            return Response(status_code=403)

    try:
        payload = json.loads(raw)
    except Exception:
        return Response(status_code=200)

    background.add_task(process_payload, payload)   # contestamos 200 ya; procesamos atrás
    return Response(status_code=200)


# =============================================================================
# 2) PROCESAMIENTO
# =============================================================================
async def process_payload(payload: dict):
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                field = change.get("field")
                value = change.get("value", {})
                if field == "messages":
                    await process_change(value)            # mensaje ENTRANTE del cliente
                elif field == "smb_message_echoes":
                    await process_echo(value)              # COEXISTENCE: el agente desde su celular
                elif field in ("history", "smb_app_state_sync"):
                    log.info("Coexistence sync '%s' recibido.", field)  # opcional: precargar historial
    except Exception as e:
        log.exception("Error procesando webhook: %s", e)


async def process_change(value: dict):
    metadata = value.get("metadata", {})
    phone_number_id = metadata.get("phone_number_id")
    numero = await resolve_number(phone_number_id)
    if not numero:
        log.warning("Número no registrado en wa_numbers: %s — ignorado", phone_number_id)
        return
    user_id = numero["user_id"]
    token   = numero.get("access_token")

    contacts = value.get("contacts", [])
    profile_name = contacts[0].get("profile", {}).get("name") if contacts else None

    for msg in value.get("messages", []):
        wamid = msg.get("id")
        if not wamid or await already_processed(wamid):
            continue

        from_wa = msg.get("from")
        referral = msg.get("referral")

        if msg.get("type") != "text":
            body = f"[{msg.get('type')}]"
            contact = await upsert_contact(user_id, from_wa, profile_name)
            conv = await get_or_create_conversation(user_id, contact, referral, phone_number_id)
            await store_message(user_id, contact["id"], conv["id"], wamid, "in", "lead", body)
            if conv.get("ai_enabled", True):
                await wa_send_text(phone_number_id, from_wa,
                                   "Gracias por tu mensaje. Por aquí te leo mejor en texto, "
                                   "¿me cuentas qué estás buscando?", token=token)
            continue

        body = msg.get("text", {}).get("body", "").strip()
        contact = await upsert_contact(user_id, from_wa, profile_name)
        conv = await get_or_create_conversation(user_id, contact, referral, phone_number_id)
        await store_message(user_id, contact["id"], conv["id"], wamid, "in", "lead", body)

        if not conv.get("ai_enabled", True):
            continue  # el agente tomó el control

        history = await fetch_history(conv["id"])
        agente  = await perfil_agente(user_id, numero.get("waba_name"))
        result  = await recepcion_responde(history, conv.get("property_ctx"), agente)
        reply   = (result or {}).get("reply")

        # anti-choque: si el agente contestó desde su cel mientras tanto, la IA ya no manda
        if reply and await ai_sigue_encendida(conv["id"]):
            sent = await wa_send_text(phone_number_id, from_wa, reply, token=token)
            out_id = (sent.get("messages") or [{}])[0].get("id")
            await store_message(user_id, contact["id"], conv["id"], out_id or f"local-{wamid}", "out", "ai", reply)

        await actualizar_calificacion(contact["id"], result)


async def process_echo(value: dict):
    """COEXISTENCE: el agente respondió desde la app de WhatsApp en su celular.
    Lo guardamos como mensaje del agente y APAGAMOS la IA en esa conversación.
    (La estructura del echo puede variar; se lee defensivo y se loguea el crudo.)"""
    metadata = value.get("metadata", {})
    phone_number_id = metadata.get("phone_number_id")
    user_id = await resolve_user(phone_number_id)
    if not user_id:
        return

    echoes = value.get("message_echoes") or value.get("messages") or []
    if not echoes:
        log.info("Echo sin mensajes (revisar estructura): %s", json.dumps(value)[:600])
        return

    for echo in echoes:
        wamid = echo.get("id")
        to_wa = echo.get("to") or echo.get("recipient_id")
        if not to_wa or (wamid and await already_processed(wamid)):
            continue
        body = echo.get("text", {}).get("body", "") if echo.get("type") == "text" else f"[{echo.get('type','mensaje')}]"

        contact = await upsert_contact(user_id, to_wa, None)
        conv = await get_or_create_conversation(user_id, contact, None, phone_number_id)
        await store_message(user_id, contact["id"], conv["id"], wamid or f"echo-{to_wa}", "out", "agent", body)
        await sb_patch("wa_conversations", {"id": f"eq.{conv['id']}"}, {"ai_enabled": False})


# =============================================================================
# 3) RECEPCIÓN (la IA)  ->  Anthropic, responde y califica de una
# =============================================================================
async def perfil_agente(user_id: str, waba_name: str | None = None) -> dict:
    """Cómo se presenta la IA ante el prospecto. Cadena de respaldo:
        1. usuarios.nombre_publico  — lo que el agente configuró en Mi Sitio
        2. waba_name                — el nombre de SU cuenta de WhatsApp Business
        3. genérico neutro          — nunca el nombre de otra inmobiliaria

    El default global NO puede ser una empresa real: un agente sin perfil
    terminaba presentándose como Grupo Navarro ante sus propios prospectos.
    Un respaldo que se confunde con un valor legítimo además hace imposible
    detectar en logs quién no ha llenado su perfil."""
    nombre = ""
    zona   = ""
    try:
        rows = await sb_get("usuarios", {
            "id": f"eq.{user_id}",
            "select": "nombre_publico,zona_cobertura",
            "limit": "1",
        })
        if rows:
            nombre = (rows[0].get("nombre_publico") or "").strip()
            zona   = (rows[0].get("zona_cobertura") or "").strip()
    except Exception as e:
        log.warning("No se pudo leer el perfil de %s: %s", user_id, e)

    if not nombre:
        nombre = (waba_name or "").strip()
    if not nombre:
        nombre = "tu asesor inmobiliario"
        log.info("Usuario %s sin nombre_publico ni waba_name — la IA usa genérico", user_id)

    return {"nombre": nombre, "zona": zona}


async def recepcion_responde(history: list, property_ctx: str | None,
                             agente: dict | None = None) -> dict:
    agente = agente or {"nombre": "tu asesor inmobiliario", "zona": ""}
    quien  = agente["nombre"]
    zona   = agente.get("zona") or ""
    ubica  = f" en {zona}" if zona else ""

    contexto = property_ctx or (
        f"Atiendes prospectos de {quien}, asesor inmobiliario{ubica}. "
        "Si no sabes por qué propiedad escribe, pregúntale qué busca."
    )
    system = (
        f"Eres 'Recepción', el asistente de WhatsApp de {quien}, asesor inmobiliario{ubica}. "
        "Atiendes a un prospecto que escribió por un anuncio. Califícalo con calidez y rapidez, sin sonar "
        "a robot ni a interrogatorio: averigua forma de pago o crédito, presupuesto real, para cuándo lo "
        "necesita y qué busca; cuando haga sentido, ofrece agendar una visita con día y hora. Español "
        "mexicano, cálido y profesional, mensajes cortos de WhatsApp, sin emojis.\n\n"
        f"Contexto: {contexto}\n\n"
        "Responde ÚNICAMENTE con un JSON válido, sin texto antes ni después, así:\n"
        '{"reply":"el mensaje para el prospecto","temperatura":"Caliente|Tibio|Frío",'
        '"score":0-100,"presupuesto":"texto o null","forma_pago":"crédito|contado|por definir",'
        '"busca":"1 frase o null","listo_para_visita":true,"resumen":"1 frase para el agente"}'
    )

    # Anthropic exige que el hilo empiece en 'user': quitamos assistants iniciales
    msgs = list(history)
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs:
        msgs = [{"role": "user", "content": "Hola"}]

    try:
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post(
                f"{ANTHROPIC_BASE}/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY,
                         "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
                json={"model": RECEPCION_MODEL, "max_tokens": 600, "system": system, "messages": msgs},
            )
            data = r.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
            if not text:
                log.error("Anthropic sin texto (status %s): %s", r.status_code, json.dumps(data)[:500])
                raise ValueError("respuesta vacia de Anthropic")
            t = text.replace("```json", "").replace("```", "").strip()
            s, e = t.find("{"), t.rfind("}")           # extrae el JSON aunque venga con texto alrededor
            if s != -1 and e != -1:
                t = t[s:e + 1]
            return json.loads(t)
    except Exception as e:
        log.exception("Error en Recepción (Anthropic): %s", e)
        return {"reply": "¡Hola! Gracias por escribir. ¿Me cuentas qué estás buscando y para cuándo, "
                         "y con gusto te ayudo?",
                "temperatura": "Tibio", "score": 50, "presupuesto": None,
                "forma_pago": "por definir", "busca": None,
                "listo_para_visita": False, "resumen": "Prospecto nuevo, sin calificar aún."}


# =============================================================================
# 4) ENVÍO POR WHATSAPP (Cloud API)
# =============================================================================
def _normaliza_mx(num: str) -> str:
    """México: el wa_id que manda WhatsApp a veces trae un '1' extra después del 52
    (52 1 XXXXXXXXXX = 13 dígitos). Para ENVIAR hay que usar 52 + 10 dígitos, sin ese 1.
    Si no, Meta lo trata como número distinto (y en la sandbox, 'no autorizado')."""
    n = "".join(ch for ch in str(num) if ch.isdigit())
    if n.startswith("521") and len(n) == 13:
        n = "52" + n[3:]
    return n


async def wa_send_text(phone_number_id: str, to: str, body: str, token: str | None = None) -> dict:
    """token: el access_token del usuario dueño del número. Si no se pasa, se busca
    en wa_numbers. WHATSAPP_TOKEN (global) queda solo como último recurso para el
    piloto; con multi-tenant cada número manda con SU propio token de negocio."""
    if not token:
        row = await resolve_number(phone_number_id)
        token = (row or {}).get("access_token") or WHATSAPP_TOKEN
    if not token:
        log.error("Sin token para phone_number_id=%s — no se envía", phone_number_id)
        return {}

    to = _normaliza_mx(to)
    log.info("WhatsApp enviando a %s", to)
    url = f"{GRAPH_API}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(url, headers=headers, json=data)
            if r.status_code >= 400:
                log.error("WhatsApp send error %s: %s", r.status_code, r.text)
            return r.json()
    except Exception as e:
        log.exception("Error enviando WhatsApp: %s", e)
        return {}


# =============================================================================
# 5) ENDPOINT PARA LA BANDEJA  ->  el agente manda un mensaje a mano
# =============================================================================
class SendReq(BaseModel):
    conversation_id: str
    body: str


@router.post("/send")
async def agent_send(req: SendReq, request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sesión inválida")

    convs = await sb_get("wa_conversations",
                         {"id": f"eq.{req.conversation_id}", "user_id": f"eq.{user_id}", "limit": "1"})
    if not convs:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv = convs[0]

    cs = await sb_get("wa_contacts", {"id": f"eq.{conv['contact_id']}", "select": "wa_id", "limit": "1"})
    if not cs:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    to = cs[0]["wa_id"]

    sent = await wa_send_text(conv["phone_number_id"], to, req.body)
    out_id = (sent.get("messages") or [{}])[0].get("id")
    await store_message(user_id, conv["contact_id"], conv["id"],
                        out_id or f"agent-{_now()}", "out", "agent", req.body)
    # el humano contestó -> apagamos la IA en esta conversación
    await sb_patch("wa_conversations", {"id": f"eq.{conv['id']}"}, {"ai_enabled": False})
    return {"ok": True, "wa_message_id": out_id}


# =============================================================================
# 6) Funciones de datos
# =============================================================================
async def resolve_number(phone_number_id: str | None) -> dict | None:
    """Devuelve la fila completa de wa_numbers (user_id, access_token, ia_enabled...).
    SIN fallback a DEFAULT_USER_ID: un número no mapeado se ignora. Antes caía en la
    cuenta del piloto, lo que en multi-tenant es una fuga de datos entre clientes."""
    if not phone_number_id:
        return None
    rows = await sb_get("wa_numbers", {
        "phone_number_id": f"eq.{phone_number_id}",
        "select": "user_id,access_token,ia_enabled,waba_id,waba_name",
        "limit": "1",
    })
    return rows[0] if rows else None


async def resolve_user(phone_number_id: str | None) -> str | None:
    row = await resolve_number(phone_number_id)
    return row["user_id"] if row else None


async def already_processed(wamid: str) -> bool:
    rows = await sb_get("wa_messages", {"wa_message_id": f"eq.{wamid}", "select": "id", "limit": "1"})
    return bool(rows)


async def upsert_contact(user_id, wa_id, nombre):
    rows = await sb_get("wa_contacts",
                        {"user_id": f"eq.{user_id}", "wa_id": f"eq.{wa_id}", "limit": "1"})
    if rows:
        contact = rows[0]
        if nombre and not contact.get("nombre"):
            await sb_patch("wa_contacts", {"id": f"eq.{contact['id']}"}, {"nombre": nombre})
            contact["nombre"] = nombre
        return contact
    created = await sb_post("wa_contacts",
                            {"user_id": user_id, "wa_id": wa_id, "nombre": nombre,
                             "temperatura": "Nuevo", "score": 0, "etapa": "Nuevo"})
    return created[0] if created else {"id": None}


async def get_or_create_conversation(user_id, contact, referral, phone_number_id):
    rows = await sb_get("wa_conversations", {"contact_id": f"eq.{contact['id']}", "limit": "1"})
    if rows:
        return rows[0]
    property_ctx = None
    if referral:
        headline = referral.get("headline", "")
        bodytext = referral.get("body", "")
        property_ctx = f"El prospecto escribió por el anuncio: '{headline}'. {bodytext}".strip()
    created = await sb_post("wa_conversations",
                            {"user_id": user_id, "contact_id": contact["id"],
                             "phone_number_id": phone_number_id, "ai_enabled": True,
                             "property_ctx": property_ctx})
    return created[0] if created else {"id": None, "ai_enabled": True}


async def store_message(user_id, contact_id, conversation_id, wa_message_id, direction, sender, body):
    await sb_post("wa_messages",
                  {"user_id": user_id, "contact_id": contact_id, "conversation_id": conversation_id,
                   "wa_message_id": wa_message_id, "direction": direction, "sender": sender, "body": body},
                  prefer="return=minimal")
    await sb_patch("wa_conversations", {"id": f"eq.{conversation_id}"}, {"last_message_at": _now()})


async def fetch_history(conversation_id) -> list:
    rows = await sb_get("wa_messages",
                        {"conversation_id": f"eq.{conversation_id}", "select": "sender,body",
                         "order": "created_at.desc", "limit": str(HISTORY_LIMIT)})
    rows = list(reversed(rows or []))
    return [{"role": "user" if r["sender"] == "lead" else "assistant", "content": r["body"]} for r in rows]


async def actualizar_calificacion(contact_id, result: dict):
    if not result:
        return
    campos = {}
    for k in ("temperatura", "score", "presupuesto", "forma_pago", "busca", "resumen"):
        if result.get(k) is not None:
            campos[k] = result[k]
    if result.get("listo_para_visita"):
        campos["etapa"] = "Cita"
    if campos:
        campos["updated_at"] = _now()
        await sb_patch("wa_contacts", {"id": f"eq.{contact_id}"}, campos)


async def ai_sigue_encendida(conversation_id) -> bool:
    rows = await sb_get("wa_conversations",
                        {"id": f"eq.{conversation_id}", "select": "ai_enabled", "limit": "1"})
    return bool(rows) and rows[0].get("ai_enabled", True)


# =============================================================================
# 6) ENDPOINTS PARA EL MÓDULO WHATSAPP (conexión por agente)
# =============================================================================

META_APP_ID     = os.environ.get("META_APP_ID", "")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "") or WA_APP_SECRET


# ── /whatsapp/status ─────────────────────────────────────────────────────────
@router.get("/status")
async def wa_status(request: Request):
    """Devuelve si el usuario tiene un número conectado."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")
    rows = await sb_get("wa_numbers", {"user_id": f"eq.{user_id}", "select": "*", "limit": "1"})
    if not rows:
        return {"connected": False}
    row = rows[0]
    return {
        "connected":    True,
        "phone_number": row.get("display_number", ""),
        "waba_name":    row.get("waba_name", "WhatsApp Business"),
        "ia_enabled":   row.get("ia_enabled", True),
    }


# ── /whatsapp/connect ─────────────────────────────────────────────────────────
class ConnectReq(BaseModel):
    code: str
    waba_id: str | None = None
    phone_number_id: str | None = None
    coexistence: bool = False


@router.post("/connect")
async def wa_connect(req: ConnectReq, request: Request):
    """Cierra el Embedded Signup: intercambia el code por un business token y
    registra el número del cliente.

    OJO — esto NO es el OAuth clásico:
      · El intercambio va SIN redirect_uri (el ES usa el SDK de JS, no redirect).
      · El token que regresa es un business integration system user access token,
        ligado a la integración, no un user token de 2 horas.
      · waba_id y phone_number_id los devuelve el propio flujo de ES al frontend;
        no hay que ir a adivinarlos recorriendo /me/businesses.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    if not META_APP_ID or not META_APP_SECRET:
        raise HTTPException(status_code=500, detail="META_APP_ID o META_APP_SECRET no configurados")

    # 1) code -> business token  (sin redirect_uri: es Embedded Signup)
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{GRAPH_API}/oauth/access_token", params={
            "client_id":     META_APP_ID,
            "client_secret": META_APP_SECRET,
            "code":          req.code,
        })
        if r.status_code != 200:
            log.error("Meta token error %s: %s", r.status_code, r.text)
            raise HTTPException(status_code=400, detail="No se pudo obtener el token de Meta")
        tok = r.json()
        business_token = tok.get("access_token", "")
        expires_in     = tok.get("expires_in")

    if not business_token:
        raise HTTPException(status_code=400, detail="Meta no devolvió un token de acceso")

    waba_id         = (req.waba_id or "").strip()
    phone_number_id = (req.phone_number_id or "").strip()

    # 2) Si el frontend no los mandó, se leen con el business token (fallback)
    if not waba_id:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{GRAPH_API}/debug_token", params={
                "input_token":  business_token,
                "access_token": f"{META_APP_ID}|{META_APP_SECRET}",
            })
            if r.status_code == 200:
                scopes = r.json().get("data", {}).get("granular_scopes", [])
                for s in scopes:
                    if s.get("scope") == "whatsapp_business_management":
                        ids = s.get("target_ids") or []
                        if ids:
                            waba_id = ids[0]
                            break
    if not waba_id:
        raise HTTPException(status_code=400, detail="No se pudo identificar la cuenta de WhatsApp Business")

    # 3) Datos del número
    waba_name    = "WhatsApp Business"
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
        phone_number    = (phones[0].get("display_phone_number") or "").replace("+", "").replace(" ", "")

    if not phone_number_id:
        raise HTTPException(status_code=400,
                            detail="No se encontró un número en tu cuenta de WhatsApp Business")

    # 4) Guardar. El upsert va por phone_number_id (tiene unique), NO por user_id:
    #    así un número que cambia de dueño no duplica fila.
    payload = {
        "user_id":         user_id,
        "phone_number_id": phone_number_id,
        "display_number":  phone_number,
        "waba_id":         waba_id,
        "waba_name":       waba_name,
        "access_token":    business_token,
        "ia_enabled":      True,
        "updated_at":      _now(),
    }
    if expires_in:
        try:
            payload["token_expires_at"] = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + int(expires_in), timezone.utc).isoformat()
        except Exception:
            pass

    existing = await sb_get("wa_numbers",
                            {"phone_number_id": f"eq.{phone_number_id}", "select": "id", "limit": "1"})
    if existing:
        await sb_patch("wa_numbers", {"phone_number_id": f"eq.{phone_number_id}"}, payload)
    else:
        payload["created_at"] = _now()
        await sb_post("wa_numbers", payload)

    # 5) Suscribir la app al webhook de ESA WABA (sin esto no llegan mensajes)
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{GRAPH_API}/{waba_id}/subscribed_apps",
                         params={"access_token": business_token})
        if r.status_code >= 400:
            log.error("No se pudo suscribir el webhook de %s: %s", waba_id, r.text)

    # 6) Registrar el número en Cloud API.
    #    En COEXISTENCIA se SALTA: el número ya está registrado por la app de
    #    WhatsApp Business y llamar a /register aquí rompe el vínculo.
    if req.coexistence:
        log.info("Coexistencia: se omite /register para %s (ya registrado)", phone_number_id)
    else:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{GRAPH_API}/{phone_number_id}/register",
                             params={"access_token": business_token},
                             json={"messaging_product": "whatsapp", "pin": WA_REGISTER_PIN})
            if r.status_code >= 400:
                log.warning("Registro de %s: %s", phone_number_id, r.text)

    log.info("WhatsApp conectado: user=%s waba=%s phone=%s coex=%s",
             user_id, waba_id, phone_number, req.coexistence)
    return {"ok": True, "phone_number": phone_number, "waba_name": waba_name,
            "coexistence": req.coexistence}


# ── /whatsapp/ia-global ───────────────────────────────────────────────────────
class IAGlobalReq(BaseModel):
    ia_enabled: bool

@router.patch("/ia-global")
async def wa_ia_global(req: IAGlobalReq, request: Request):
    """Enciende o apaga Recepción para todas las conversaciones del usuario."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")
    await sb_patch("wa_numbers", {"user_id": f"eq.{user_id}"}, {
        "ia_enabled": req.ia_enabled,
        "updated_at": _now(),
    })
    # Propagar a todas las conversaciones activas
    await sb_patch("wa_conversations", {"user_id": f"eq.{user_id}"}, {
        "ai_enabled": req.ia_enabled,
        "updated_at": _now(),
    })
    return {"ok": True, "ia_enabled": req.ia_enabled}


# ── /whatsapp/disconnect ──────────────────────────────────────────────────────
@router.delete("/disconnect")
async def wa_disconnect(request: Request):
    """Desvincula el número de WhatsApp del usuario. No elimina conversaciones."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    # Obtener info antes de borrar (para revocar token en Meta)
    rows = await sb_get("wa_numbers", {"user_id": f"eq.{user_id}", "select": "*", "limit": "1"})
    if rows:
        token = rows[0].get("access_token", "")
        # Intentar revocar en Meta (best-effort, no bloquea si falla)
        if token:
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    await c.delete(f"https://graph.facebook.com/v21.0/me/permissions",
                                   params={"access_token": token})
            except Exception:
                pass

    # Eliminar el registro (las conversaciones y contactos se quedan)
    async with httpx.AsyncClient(timeout=15) as c:
        h = _sb_headers()
        await c.delete(f"{SUPABASE_URL}/rest/v1/wa_numbers",
                       headers=h, params={"user_id": f"eq.{user_id}"})

    log.info("WhatsApp desconectado: user=%s", user_id)
    return {"ok": True}


# =============================================================================
# 7) PLANTILLAS DE MENSAJE (Message Templates)
# =============================================================================
# Las plantillas son obligatorias para escribirle primero a un contacto
# (fuera de la ventana de 24h) y para los mensajes de seguimiento/marketing.
# Meta las revisa y aprueba antes de poder usarlas.

class TemplateComponent(BaseModel):
    type: str          # "BODY", "HEADER", "FOOTER", "BUTTONS"
    text: str | None = None
    format: str | None = None   # para HEADER: "TEXT", "IMAGE", "VIDEO", "DOCUMENT"
    buttons: list[dict] | None = None

class TemplateCreateReq(BaseModel):
    name: str                      # solo minúsculas, números y guion_bajo
    category: str                  # "UTILITY", "MARKETING", "AUTHENTICATION"
    language: str = "es_MX"
    body_text: str                 # texto del cuerpo, puede incluir {{1}}, {{2}}...
    header_text: str | None = None
    footer_text: str | None = None
    example_body_params: list[str] | None = None   # ejemplo para cada {{n}} del cuerpo


async def _waba_id_y_token(user_id: str) -> tuple[str, str]:
    """Obtiene el waba_id y el token de acceso del usuario."""
    rows = await sb_get("wa_numbers", {"user_id": f"eq.{user_id}", "select": "waba_id,access_token", "limit": "1"})
    if not rows or not rows[0].get("waba_id"):
        raise HTTPException(status_code=400, detail="No tienes un número de WhatsApp conectado")
    waba_id = rows[0]["waba_id"]
    token = rows[0].get("access_token") or WHATSAPP_TOKEN
    if not token:
        raise HTTPException(status_code=400, detail="No hay token de acceso configurado")
    return waba_id, token


# ── GET /whatsapp/templates — listar plantillas existentes ───────────────────
@router.get("/templates")
async def list_templates(request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    waba_id, token = await _waba_id_y_token(user_id)

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(
            f"{GRAPH_API}/{waba_id}/message_templates",
            params={"access_token": token, "limit": "50"},
        )
    if r.status_code != 200:
        log.error("Error listando templates: %s", r.text)
        raise HTTPException(status_code=400, detail="No se pudieron obtener las plantillas")

    data = r.json().get("data", [])
    out = []
    for t in data:
        out.append({
            "id":       t.get("id"),
            "name":     t.get("name"),
            "status":   t.get("status"),       # APPROVED / PENDING / REJECTED
            "category": t.get("category"),
            "language": t.get("language"),
        })
    return {"templates": out}


# ── POST /whatsapp/templates — crear una plantilla nueva ─────────────────────
@router.post("/templates")
async def create_template(req: TemplateCreateReq, request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    nombre = "".join(ch for ch in req.name.lower().strip().replace(" ", "_") if ch.isalnum() or ch == "_")
    if not nombre:
        raise HTTPException(status_code=400, detail="Nombre de plantilla inválido")

    waba_id, token = await _waba_id_y_token(user_id)

    components = []

    if req.header_text:
        components.append({"type": "HEADER", "format": "TEXT", "text": req.header_text})

    body_comp = {"type": "BODY", "text": req.body_text}
    if req.example_body_params:
        body_comp["example"] = {"body_text": [req.example_body_params]}
    components.append(body_comp)

    if req.footer_text:
        components.append({"type": "FOOTER", "text": req.footer_text})

    payload = {
        "name":       nombre,
        "category":   req.category.upper(),
        "language":   req.language,
        "components": components,
    }

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            f"{GRAPH_API}/{waba_id}/message_templates",
            params={"access_token": token},
            json=payload,
        )

    if r.status_code not in (200, 201):
        log.error("Error creando template: %s", r.text)
        try:
            detail = r.json().get("error", {}).get("error_user_msg") or r.json().get("error", {}).get("message")
        except Exception:
            detail = "Meta rechazó la plantilla"
        raise HTTPException(status_code=400, detail=detail or "No se pudo crear la plantilla")

    data = r.json()
    log.info("Template creado: user=%s name=%s id=%s", user_id, nombre, data.get("id"))
    return {"ok": True, "id": data.get("id"), "status": data.get("status", "PENDING"), "name": nombre}


# ── DELETE /whatsapp/templates/{name} — eliminar plantilla ───────────────────
@router.delete("/templates/{name}")
async def delete_template(name: str, request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    waba_id, token = await _waba_id_y_token(user_id)

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.delete(
            f"{GRAPH_API}/{waba_id}/message_templates",
            params={"access_token": token, "name": name},
        )

    if r.status_code != 200:
        log.error("Error borrando template: %s", r.text)
        raise HTTPException(status_code=400, detail="No se pudo eliminar la plantilla")

    return {"ok": True}


# ── POST /whatsapp/templates/{name}/send — enviar una plantilla a un contacto ─
class TemplateSendReq(BaseModel):
    to: str
    template_name: str
    language: str = "es_MX"
    body_params: list[str] | None = None

@router.post("/templates/send")
async def send_template(req: TemplateSendReq, request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    rows = await sb_get("wa_numbers", {"user_id": f"eq.{user_id}", "select": "phone_number_id,access_token", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=400, detail="No tienes un número de WhatsApp conectado")
    phone_number_id = rows[0]["phone_number_id"]
    token = rows[0].get("access_token") or WHATSAPP_TOKEN

    to = _normaliza_mx(req.to)

    components = []
    if req.body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in req.body_params],
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": req.template_name,
            "language": {"code": req.language},
            "components": components,
        },
    }

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            f"{GRAPH_API}/{phone_number_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )

    if r.status_code != 200:
        log.error("Error enviando template: %s", r.text)
        raise HTTPException(status_code=400, detail="No se pudo enviar la plantilla")

    return {"ok": True, "wamid": r.json().get("messages", [{}])[0].get("id")}
