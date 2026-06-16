# =============================================================================
# Broquer · Módulo WhatsApp (Recepción)
# -----------------------------------------------------------------------------
# Qué hace este archivo:
#   1. Recibe los mensajes que llegan al WhatsApp del agente (webhook de Meta).
#   2. Los guarda en Supabase (contacto + conversación + mensajes).
#   3. "Recepción" (la IA) lee el hilo, responde por WhatsApp y va calificando
#      al prospecto en automático.
#   4. Si el agente toma el control de una conversación (ai_enabled = false),
#      la IA se calla y deja que conteste el humano.
#
# Cómo se conecta a tu app (ver INSTALACION.md para el detalle):
#   from whatsapp import router as whatsapp_router
#   app.include_router(whatsapp_router)
#
# Dependencias:  pip install fastapi requests supabase openai
# =============================================================================

import os
import json
import hmac
import hashlib
import logging

import requests
from fastapi import APIRouter, Request, Response, BackgroundTasks
from supabase import create_client, Client
from openai import OpenAI

log = logging.getLogger("broquer.whatsapp")

# -----------------------------------------------------------------------------
# CONFIGURACIÓN  (todo se lee de variables de entorno en Railway)
# -----------------------------------------------------------------------------
GRAPH_API = "https://graph.facebook.com/v21.0"

# --- WhatsApp / Meta ---
WHATSAPP_TOKEN   = os.environ.get("WHATSAPP_TOKEN")          # token permanente del System User
WA_VERIFY_TOKEN  = os.environ.get("WA_VERIFY_TOKEN", "broquer_verify")  # lo inventas tú; debe coincidir con Meta
WA_APP_SECRET    = os.environ.get("WA_APP_SECRET")           # opcional: para validar la firma del webhook

# --- Supabase ---
SUPABASE_URL         = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # la service_role key (solo backend)
# Si ya tienes un cliente de Supabase en tu app, usa ese y borra estas 2 líneas:
sb: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# --- Cerebro / LLM (Groq por defecto; sirve cualquiera compatible con OpenAI) ---
LLM_API_KEY  = os.environ.get("LLM_API_KEY")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL    = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
llm = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

# --- Piloto (un solo agente mientras pruebas con Grupo Navarro) ---
# En producción multiagente, el dueño se resuelve por el número (tabla wa_numbers).
DEFAULT_OWNER_ID = os.environ.get("DEFAULT_OWNER_ID")  # uuid del agente piloto
DEFAULT_AGENCIA  = os.environ.get("DEFAULT_AGENCIA", "Grupo Navarro")

# Cuántos mensajes del hilo le pasamos a la IA como contexto
HISTORY_LIMIT = 14

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


# =============================================================================
# 1) WEBHOOK
# =============================================================================
@router.get("/webhook")
def verify_webhook(request: Request):
    """Meta llama aquí UNA vez para verificar el webhook. Le regresamos el reto
    si el token coincide con el que pusiste en el panel de Meta."""
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == WA_VERIFY_TOKEN:
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    return Response(content="forbidden", status_code=403)


@router.post("/webhook")
async def receive_webhook(request: Request, background: BackgroundTasks):
    """Aquí caen TODOS los mensajes entrantes. Importante: le contestamos 200 a
    Meta de inmediato y procesamos en segundo plano, para que no reintente."""
    raw = await request.body()

    # Validación de firma (opcional pero recomendada). Si no pusiste WA_APP_SECRET,
    # se salta.
    if WA_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(WA_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            log.warning("Firma de webhook inválida")
            return Response(status_code=403)

    try:
        payload = json.loads(raw)
    except Exception:
        return Response(status_code=200)  # nunca tronar el webhook

    # Procesamos en segundo plano (la IA puede tardar unos segundos)
    background.add_task(process_payload, payload)
    return Response(status_code=200)


# =============================================================================
# 2) PROCESAMIENTO  (corre en segundo plano)
# =============================================================================
def process_payload(payload: dict):
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                field = change.get("field")
                value = change.get("value", {})
                if field == "messages":
                    process_change(value)          # mensaje ENTRANTE del cliente
                elif field == "smb_message_echoes":
                    process_echo(value)            # COEXISTENCE: lo que el agente mandó desde su CELULAR
                elif field in ("history", "smb_app_state_sync"):
                    process_sync(field, value)     # COEXISTENCE: backfill al conectar (opcional)
    except Exception as e:
        log.exception("Error procesando webhook: %s", e)


def process_change(value: dict):
    metadata = value.get("metadata", {})
    phone_number_id = metadata.get("phone_number_id")
    owner_id = resolve_owner(phone_number_id)

    contacts = value.get("contacts", [])
    profile_name = contacts[0].get("profile", {}).get("name") if contacts else None

    for msg in value.get("messages", []):
        wamid = msg.get("id")
        if not wamid or already_processed(wamid):
            continue  # dedupe: Meta a veces reintenta

        from_wa = msg.get("from")
        referral = msg.get("referral")  # viene si el lead llegó por un anuncio Click-to-WhatsApp

        # MVP: por ahora solo texto. Otros tipos (audio, imagen) se acusan amablemente.
        if msg.get("type") != "text":
            body = f"[{msg.get('type')}]"
            contact = upsert_contact(owner_id, from_wa, profile_name)
            conv = get_or_create_conversation(owner_id, contact, referral, phone_number_id)
            store_message(owner_id, contact, conv, wamid, "in", "lead", body)
            if conv.get("ai_enabled", True):
                send_text(phone_number_id, from_wa,
                          "Gracias por tu mensaje. Por aquí te leo mejor en texto, "
                          "¿me cuentas qué estás buscando?")
            continue

        body = msg.get("text", {}).get("body", "").strip()
        contact = upsert_contact(owner_id, from_wa, profile_name)
        conv = get_or_create_conversation(owner_id, contact, referral, phone_number_id)
        store_message(owner_id, contact, conv, wamid, "in", "lead", body)

        # Si el agente tomó el control, la IA NO contesta.
        if not conv.get("ai_enabled", True):
            continue

        # --- Recepción responde y califica ---
        history = fetch_history(conv["id"])
        result = recepcion_responde(history, conv.get("property_ctx"))

        reply = (result or {}).get("reply")
        # Re-chequeo anti-choque: si en estos segundos el agente contestó desde su
        # celular (Coexistence), la IA ya NO manda nada para no encimarse.
        if reply and ai_sigue_encendida(conv["id"]):
            sent = send_text(phone_number_id, from_wa, reply)
            out_id = sent.get("messages", [{}])[0].get("id") if sent else None
            store_message(owner_id, contact, conv, out_id or f"local-{wamid}", "out", "ai", reply)

        actualizar_calificacion(contact["id"], result)


# =============================================================================
# 2b) COEXISTENCE  ->  el agente también contesta desde su celular
# =============================================================================
def process_echo(value: dict):
    """COEXISTENCE: cuando el agente responde desde la app de WhatsApp en su cel,
    Meta nos manda un 'echo'. Lo guardamos como mensaje del agente y, sobre todo,
    APAGAMOS la IA en esa conversación: el humano tomó el control, Recepción se
    quita para no encimarse. El agente puede reactivar la IA desde la bandeja.

    Nota: la estructura exacta del echo puede variar un poquito; lo leemos de forma
    defensiva y dejamos el crudo en el log la primera vez para confirmarlo."""
    metadata = value.get("metadata", {})
    phone_number_id = metadata.get("phone_number_id")
    owner_id = resolve_owner(phone_number_id)

    echoes = value.get("message_echoes") or value.get("messages") or []
    if not echoes:
        log.info("Echo sin mensajes (revisar estructura): %s", json.dumps(value)[:600])
        return

    for echo in echoes:
        wamid = echo.get("id")
        to_wa = echo.get("to") or echo.get("recipient_id")  # el cliente al que el agente le escribió
        if not to_wa or (wamid and already_processed(wamid)):
            continue
        body = echo.get("text", {}).get("body", "") if echo.get("type") == "text" else f"[{echo.get('type','mensaje')}]"

        contact = upsert_contact(owner_id, to_wa, None)
        conv = get_or_create_conversation(owner_id, contact, None, phone_number_id)
        store_message(owner_id, contact, conv, wamid or f"echo-{to_wa}", "out", "agent", body)
        # El humano contestó -> la IA se calla en esta conversación
        sb.table("wa_conversations").update({"ai_enabled": False}).eq("id", conv["id"]).execute()


def process_sync(field: str, value: dict):
    """COEXISTENCE (opcional): al conectar, Meta manda hasta ~6 meses de historial
    ('history') y los contactos ('smb_app_state_sync'). Por ahora solo lo
    registramos para no saturar; si quieres precargar la bandeja con esos chats,
    aquí los recorremos e insertamos. (Muchas plataformas arrancan en blanco.)"""
    log.info("Webhook de Coexistence '%s' recibido (sync inicial).", field)
    # Extender aquí si quieres importar historial/contactos a wa_messages/wa_contacts.


def ai_sigue_encendida(conversation_id) -> bool:
    res = sb.table("wa_conversations").select("ai_enabled").eq("id", conversation_id).limit(1).execute()
    return bool(res.data) and res.data[0].get("ai_enabled", True)


# =============================================================================
# 3) RECEPCIÓN (la IA)  ->  responde y califica en una sola llamada
# =============================================================================
def recepcion_responde(history: list, property_ctx: str | None) -> dict:
    contexto_prop = property_ctx or (
        f"Atiendes prospectos de {DEFAULT_AGENCIA}, inmobiliaria en Morelia. "
        "Si no sabes por qué propiedad escribe, pregúntale qué busca."
    )

    system = (
        f"Eres 'Recepción', el asistente de WhatsApp de {DEFAULT_AGENCIA}, inmobiliaria en Morelia. "
        "Atiendes a un prospecto que escribió por un anuncio. Tu trabajo es calificarlo con calidez y "
        "rapidez, sin sonar a robot ni a interrogatorio: averigua forma de pago o crédito, presupuesto "
        "real, para cuándo lo necesita y qué busca; y cuando haga sentido, ofrece agendar una visita con "
        "día y hora. Hablas en español mexicano, cálido y profesional, en mensajes cortos como de "
        "WhatsApp, sin emojis.\n\n"
        f"Contexto de la propiedad / cuenta: {contexto_prop}\n\n"
        "Devuelve SIEMPRE un JSON válido, sin texto extra, con esta forma:\n"
        '{"reply":"el mensaje que le envías al prospecto",'
        '"temperatura":"Caliente|Tibio|Frío",'
        '"score":0-100,'
        '"presupuesto":"texto corto o null",'
        '"forma_pago":"crédito|contado|por definir",'
        '"busca":"1 frase o null",'
        '"listo_para_visita":true|false,'
        '"resumen":"1 frase para el agente, en español mexicano"}'
    )

    messages = [{"role": "system", "content": system}]
    messages.extend(history)

    try:
        resp = llm.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.5,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        log.exception("Error en Recepción (LLM): %s", e)
        # Fallback: no dejamos al prospecto sin respuesta
        return {"reply": "¡Hola! Gracias por escribir. ¿Me cuentas un poco qué estás buscando "
                         "y para cuándo, y con gusto te ayudo?",
                "temperatura": "Tibio", "score": 50, "presupuesto": None,
                "forma_pago": "por definir", "busca": None,
                "listo_para_visita": False, "resumen": "Prospecto nuevo, sin calificar aún."}


# =============================================================================
# 4) ENVÍO POR WHATSAPP (Cloud API)
# =============================================================================
def send_text(phone_number_id: str, to: str, body: str) -> dict:
    """Manda un mensaje de texto libre. Solo funciona dentro de la ventana de 24h
    (cuando el cliente escribió primero), que es justo el caso de Recepción."""
    url = f"{GRAPH_API}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
    try:
        r = requests.post(url, headers=headers, json=data, timeout=20)
        if r.status_code >= 400:
            log.error("WhatsApp send error %s: %s", r.status_code, r.text)
        return r.json()
    except Exception as e:
        log.exception("Error enviando WhatsApp: %s", e)
        return {}


# =============================================================================
# 5) SUPABASE  (contactos, conversaciones, mensajes)
# =============================================================================
def resolve_owner(phone_number_id: str | None) -> str | None:
    """Multiagente: cada número está mapeado a un agente en la tabla wa_numbers.
    En piloto, si no hay mapeo, usamos DEFAULT_OWNER_ID."""
    if phone_number_id:
        try:
            res = sb.table("wa_numbers").select("owner_id").eq("phone_number_id", phone_number_id).limit(1).execute()
            if res.data:
                return res.data[0]["owner_id"]
        except Exception:
            pass
    return DEFAULT_OWNER_ID


def already_processed(wamid: str) -> bool:
    res = sb.table("wa_messages").select("id").eq("wa_message_id", wamid).limit(1).execute()
    return bool(res.data)


def upsert_contact(owner_id, wa_id, nombre):
    res = sb.table("wa_contacts").select("*").eq("owner_id", owner_id).eq("wa_id", wa_id).limit(1).execute()
    if res.data:
        contact = res.data[0]
        if nombre and not contact.get("nombre"):
            sb.table("wa_contacts").update({"nombre": nombre}).eq("id", contact["id"]).execute()
            contact["nombre"] = nombre
        return contact
    nuevo = {"owner_id": owner_id, "wa_id": wa_id, "nombre": nombre,
             "temperatura": "Nuevo", "score": 0, "etapa": "Nuevo"}
    return sb.table("wa_contacts").insert(nuevo).execute().data[0]


def get_or_create_conversation(owner_id, contact, referral, phone_number_id):
    res = sb.table("wa_conversations").select("*").eq("contact_id", contact["id"]).limit(1).execute()
    if res.data:
        return res.data[0]

    property_ctx = None
    if referral:  # el lead llegó por un anuncio: guardamos de qué iba
        headline = referral.get("headline", "")
        bodytext = referral.get("body", "")
        property_ctx = f"El prospecto escribió por el anuncio: '{headline}'. {bodytext}".strip()

    nueva = {"owner_id": owner_id, "contact_id": contact["id"],
             "phone_number_id": phone_number_id, "ai_enabled": True,
             "property_ctx": property_ctx}
    return sb.table("wa_conversations").insert(nueva).execute().data[0]


def store_message(owner_id, contact, conv, wa_message_id, direction, sender, body):
    sb.table("wa_messages").insert({
        "owner_id": owner_id, "contact_id": contact["id"], "conversation_id": conv["id"],
        "wa_message_id": wa_message_id, "direction": direction, "sender": sender, "body": body,
    }).execute()
    sb.table("wa_conversations").update({"last_message_at": "now()"}).eq("id", conv["id"]).execute()


def fetch_history(conversation_id) -> list:
    """Trae los últimos mensajes y los mapea al formato del LLM
    (lead -> user, ia/agente -> assistant)."""
    res = (sb.table("wa_messages").select("sender,body")
           .eq("conversation_id", conversation_id)
           .order("created_at", desc=True).limit(HISTORY_LIMIT).execute())
    rows = list(reversed(res.data or []))
    out = []
    for r in rows:
        role = "user" if r["sender"] == "lead" else "assistant"
        out.append({"role": role, "content": r["body"]})
    return out


def actualizar_calificacion(contact_id, result: dict):
    if not result:
        return
    campos = {}
    for k in ("temperatura", "score", "presupuesto", "forma_pago", "busca", "resumen"):
        if result.get(k) is not None:
            campos[k] = result[k]
    if result.get("listo_para_visita"):
        campos["etapa"] = "Cita"
    if campos:
        campos["updated_at"] = "now()"
        sb.table("wa_contacts").update(campos).eq("id", contact_id).execute()
