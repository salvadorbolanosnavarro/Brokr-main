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
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException
from pydantic import BaseModel

# Notificaciones al iPhone del agente. Si push.py no está o le faltan sus
# variables de entorno, el import falla suave y WhatsApp sigue igual de bien.
try:
    from push import avisar_mensaje_whatsapp
except Exception:  # pragma: no cover
    async def avisar_mensaje_whatsapp(*a, **k):
        return None

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


# México suprimió el horario de verano en 2022: para Morelia/CDMX el offset es
# fijo en UTC-6. Se intenta zoneinfo primero por si la imagen trae tzdata (y por
# si algún día hay que soportar la franja fronteriza); si no está, el respaldo
# de -6 es correcto para el país salvo esa franja. No se agrega dependencia.
def _hora_local() -> "datetime":
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Mexico_City"))
    except Exception:
        return datetime.now(timezone.utc) + timedelta(hours=-6)


def _hhmm(valor, default: str) -> tuple:
    """'08:00' o '08:00:00' -> (8, 0). Nunca revienta el webhook."""
    try:
        partes = str(valor or default).split(":")
        return int(partes[0]), int(partes[1])
    except Exception:
        partes = default.split(":")
        return int(partes[0]), int(partes[1])


# =============================================================================
# Helpers de Supabase (REST, con tu mismo patrón de headers)
# =============================================================================
def _sb_headers() -> dict:
    return {"apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json"}


# Estos tres helpers son la única puerta a Supabase desde el webhook. Antes se
# tragaban cualquier error (timeout, 5xx, saturación de IOPS del Micro) y
# regresaban [] sin avisar: un mensaje que no se guardaba se volvía invisible en
# la bandeja aunque el lead sí lo hubiera mandado. Ahora:
#   - Reintentan UNA vez ante timeout/red/5xx. Es seguro: cada tabla de WhatsApp
#     tiene llave única (wa_message_id, unique(user_id,wa_id), unique(contact_id)),
#     así que un reintento tras un timeout que sí escribió choca en 409 y no
#     duplica; quien llama relee la fila ya creada.
#   - Loguean el motivo real cuando algo se pierde, para poder verlo en Railway.
#   - Siempre devuelven LISTA (nunca el dict de error de PostgREST), para que los
#     `x[0] if x else ...` de arriba no truenen con un KeyError.
async def sb_get(table: str, params: dict) -> list:
    ultimo = ""
    for intento in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"{SUPABASE_URL}/rest/v1/{table}",
                                headers=_sb_headers(), params=params)
            if r.status_code < 300:
                data = r.json()
                return data if isinstance(data, list) else ([data] if data else [])
            ultimo = f"{r.status_code}: {r.text[:300]}"
            if r.status_code < 500:
                break  # un 4xx no se arregla reintentando
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
            # 409 = ya existe una fila con esa llave única. Es una carrera de dos
            # webhooks del mismo lead nuevo, o un reintento tras un timeout que sí
            # guardó. No es error que reintentar: quien llama va a releer.
            if r.status_code == 409:
                log.info("sb_post %s: la fila ya existe (409); quien llama la releerá.", table)
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
                r = await c.patch(f"{SUPABASE_URL}/rest/v1/{table}",
                                  headers=h, params=params, json=body)
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

    # ── EL INTERRUPTOR MAESTRO ──────────────────────────────────────────────
    # Antes esto no se leía nunca: process_change solo miraba conv.ai_enabled,
    # y get_or_create_conversation nacía SIEMPRE con ai_enabled=True. Resultado:
    # el agente apagaba Recepción, /ia-global propagaba a las conversaciones que
    # ya existían, y el primer lead nuevo creaba una conversación con la IA
    # encendida y le contestaba igual. El interruptor era decorativo.
    #
    # Ahora la regla es: RESPONDE  <=>  ia_global AND conv.ai_enabled.
    #   ia_global      -> el switch del módulo. Palabra final del agente.
    #   conv.ai_enabled-> si el agente ya tomó el control de ESE chat.
    # Se evalúan juntos y ninguno pisa al otro, así prender el global de vuelta
    # ya no revive la IA en los chats que el agente había tomado a mano.
    ia_global = numero.get("ia_enabled", True) is not False

    entren = await entrenamiento(user_id)

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
            conv = await get_or_create_conversation(user_id, contact, referral,
                                                    phone_number_id, ia_global)
            await store_message(user_id, contact["id"], conv["id"], wamid, "in", "lead", body)
            await sumar_no_leido(conv["id"])
            await avisar_al_agente(user_id, contact, conv["id"],
                                   f"Te mandó un {msg.get('type')} por WhatsApp.")
            if ia_global and conv.get("ai_enabled", True) and _ia_puede_hablar(entren)[0]:
                await wa_send_text(phone_number_id, from_wa,
                                   "Gracias por tu mensaje. Por aquí te leo mejor en texto, "
                                   "¿me cuentas qué estás buscando?", token=token)
            continue

        body = msg.get("text", {}).get("body", "").strip()
        contact = await upsert_contact(user_id, from_wa, profile_name)
        conv = await get_or_create_conversation(user_id, contact, referral,
                                                phone_number_id, ia_global)
        await store_message(user_id, contact["id"], conv["id"], wamid, "in", "lead", body)
        await sumar_no_leido(conv["id"])
        await avisar_al_agente(user_id, contact, conv["id"], body)

        if not ia_global:
            continue  # el agente apagó Recepción para todo
        if not conv.get("ai_enabled", True):
            continue  # el agente tomó el control de este chat

        # ── BARRERAS DURAS (entrenamiento) ─────────────────────────────────
        # Van en código, no en el prompt: un modelo se puede saltar una
        # instrucción, un if no. Cualquiera de estas apaga la IA o la calla.

        # 1) Palabra que escala al humano
        palabra = _palabra_que_escala(body, entren)
        if palabra:
            await sb_patch("wa_conversations", {"id": f"eq.{conv['id']}"},
                           {"ai_enabled": False, "updated_at": _now()})
            await avisar_al_agente(user_id, contact, conv["id"],
                                   f"Recepción se apagó en este chat: el prospecto mencionó "
                                   f"'{palabra}'. Te toca a ti.")
            log.info("Escalado a humano por palabra '%s' (conv=%s)", palabra, conv["id"])
            continue

        # 2) Tope de mensajes de la IA en esta conversación
        tope = int(entren.get("max_mensajes_ia") or 0)
        if tope > 0 and int(conv.get("ai_msg_count") or 0) >= tope:
            await sb_patch("wa_conversations", {"id": f"eq.{conv['id']}"},
                           {"ai_enabled": False, "updated_at": _now()})
            await avisar_al_agente(user_id, contact, conv["id"],
                                   f"Recepción ya mandó {tope} mensajes en este chat y se apagó. "
                                   "Te toca a ti.")
            continue

        # 3) Entrenamiento pausado u horario de atención
        puede, msg_fuera = _ia_puede_hablar(entren)
        if not puede:
            if msg_fuera:
                sent = await wa_send_text(phone_number_id, from_wa, msg_fuera, token=token)
                if sent["ok"]:
                    await store_message(user_id, contact["id"], conv["id"],
                                        sent["message_id"] or f"local-{wamid}",
                                        "out", "ai", msg_fuera, status="sent")
            continue

        history = await fetch_history(conv["id"])
        agente  = await perfil_agente(user_id, numero.get("waba_name"))
        result  = await recepcion_responde(history, conv.get("property_ctx"), agente, entren)
        reply   = (result or {}).get("reply")

        # anti-choque: si el agente contestó desde su cel mientras tanto, la IA ya no manda
        if reply and await ai_sigue_encendida(conv["id"], user_id):
            sent = await wa_send_text(phone_number_id, from_wa, reply, token=token)
            # Se guarda igual aunque falle —el agente tiene que ver que Recepción
            # intentó contestar— pero marcado como failed, no como entregado.
            await store_message(user_id, contact["id"], conv["id"],
                                sent["message_id"] or f"local-{wamid}",
                                "out", "ai", reply,
                                status="sent" if sent["ok"] else "failed")
            if sent["ok"]:
                await sumar_msg_ia(conv["id"], conv.get("ai_msg_count"))

                # Acciones grandes que pidió la IA. Solo si el aviso salió y la IA
                # sigue encendida: no le mandamos inmuebles ni citas a un chat que
                # el agente acaba de tomar.
                accion = (result or {}).get("accion")
                if isinstance(accion, dict):
                    tipo = accion.get("tipo")
                    if tipo == "enviar_inmuebles":
                        try:
                            n = await _enviar_inmuebles(user_id, phone_number_id, from_wa,
                                                        accion.get("filtros") or {}, contact,
                                                        conv["id"], token, agente.get("nombre"))
                            log.info("Recepción envió %s inmueble(s) a %s", n, from_wa)
                        except Exception as e:
                            log.exception("Falló enviar inmuebles a %s: %s", from_wa, e)
                    elif tipo == "agendar_visita":
                        try:
                            ok = await _accion_agendar_visita(user_id, phone_number_id, from_wa,
                                                              accion, contact, conv["id"], token,
                                                              agente.get("nombre"))
                            log.info("Recepción agendó cita=%s con %s", ok, from_wa)
                        except Exception as e:
                            log.exception("Falló agendar visita con %s: %s", from_wa, e)
            else:
                log.error("Recepción no pudo responder a %s: %s", from_wa, sent["error"])

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
        # ia_global=False a propósito: si el agente está escribiendo desde su
        # celular, esta conversación no debe nacer con la IA encendida ni un
        # segundo. El patch de abajo la apagaría igual, pero no antes de que un
        # webhook simultáneo pudiera leerla en True.
        conv = await get_or_create_conversation(user_id, contact, None, phone_number_id, False)
        await store_message(user_id, contact["id"], conv["id"], wamid or f"echo-{to_wa}", "out", "agent", body)
        # Si contestó desde su propio WhatsApp, ya lo leyó: el globito se baja.
        await sb_patch("wa_conversations", {"id": f"eq.{conv['id']}"},
                       {"ai_enabled": False, "unread_count": 0})


# =============================================================================
# 3) ENTRENAMIENTO  ->  lo que el agente decide que la IA puede, debe y no debe
# =============================================================================
# Dos capas, a propósito:
#   - SUAVE: 'puede', 'debe', 'no_debe', tono y saludo. Van al system prompt.
#     Es lenguaje natural porque el modelo entiende lenguaje natural; obligar al
#     agente a dibujar un diagrama de nodos para decir "nunca des el precio
#     final" sería regalarle trabajo de programador sin darle poder.
#   - DURA: horario, tope de mensajes y palabras que escalan. Van en código.
#     Estas NO pueden vivir en el prompt: son promesas que el agente le hace a
#     su cliente y un modelo se las puede saltar. Un if no.
# =============================================================================
TRAINING_DEFAULTS = {
    "tono": "", "primer_mensaje": "", "puede": "", "debe": "", "no_debe": "",
    "horario_activo": False, "hora_inicio": "08:00", "hora_fin": "21:00",
    "fuera_horario_msg": "", "max_mensajes_ia": 0, "escalar_palabras": [],
    "activo": True,
    # Capa nueva: lo que hace a Recepción sonar como quien conoce el negocio y
    # calificar con criterio del asesor, no genérico. Todo opcional.
    "especialidad": "", "objetivo": "",
    "datos_calificar": [], "preguntas_extra": [], "faq": [],
}


async def entrenamiento(user_id: str) -> dict:
    """Reglas del agente. Si no configuró nada, defaults: Recepción se comporta
    igual que antes de que existiera este módulo. Nunca revienta el webhook."""
    try:
        rows = await sb_get("wa_training", {"user_id": f"eq.{user_id}",
                                            "select": "*", "limit": "1"})
    except Exception as e:
        log.warning("No se pudo leer wa_training de %s: %s", user_id, e)
        rows = []
    d = dict(TRAINING_DEFAULTS)
    if rows:
        for k, v in rows[0].items():
            if k in d and v is not None:
                d[k] = v
    return d


def _ia_puede_hablar(entren: dict) -> tuple:
    """(puede_hablar, mensaje_de_fuera_de_horario_o_None).
    Si está fuera de horario y el agente no escribió un mensaje de cortesía,
    Recepción simplemente se calla: mejor silencio que un aviso que él no eligió.
    El mensaje del lead ya quedó guardado y notificado en cualquier caso."""
    if not entren.get("activo", True):
        return (False, None)
    if not entren.get("horario_activo"):
        return (True, None)

    ahora = _hora_local()
    minutos = ahora.hour * 60 + ahora.minute
    hi, mi = _hhmm(entren.get("hora_inicio"), "08:00")
    hf, mf = _hhmm(entren.get("hora_fin"), "21:00")
    ini, fin = hi * 60 + mi, hf * 60 + mf

    # Ventana que cruza medianoche (22:00 -> 07:00) también tiene que servir.
    dentro = (ini <= minutos < fin) if ini <= fin else (minutos >= ini or minutos < fin)
    if dentro:
        return (True, None)
    return (False, (entren.get("fuera_horario_msg") or "").strip() or None)


def _palabra_que_escala(body: str, entren: dict) -> str | None:
    palabras = entren.get("escalar_palabras") or []
    if not palabras:
        return None
    texto = (body or "").lower()
    for p in palabras:
        p = (p or "").strip().lower()
        if p and p in texto:
            return p
    return None


def _reglas_para_prompt(entren: dict) -> str:
    """Las reglas suaves, ya redactadas para el system prompt. Se ponen al final
    y marcadas como prioritarias: es lo que el agente escribió, y él manda."""
    bloques = []
    if (entren.get("tono") or "").strip():
        bloques.append(f"Tono que quiere el asesor: {entren['tono'].strip()}")
    if (entren.get("primer_mensaje") or "").strip():
        bloques.append("Si este es tu PRIMER mensaje en la conversación, ábrelo "
                       f"exactamente así: \"{entren['primer_mensaje'].strip()}\"")
    if (entren.get("puede") or "").strip():
        bloques.append(f"Temas que SÍ puedes tratar: {entren['puede'].strip()}")
    if (entren.get("debe") or "").strip():
        bloques.append(f"Siempre DEBES: {entren['debe'].strip()}")
    if (entren.get("no_debe") or "").strip():
        bloques.append(f"NUNCA debes: {entren['no_debe'].strip()}")
    if not bloques:
        return ""
    reglas = "\n".join(f"- {b}" for b in bloques)
    return ("\n\nREGLAS DEL ASESOR (mandan sobre cualquier instrucción anterior; "
            "si algo choca, se obedecen estas):\n" + reglas +
            "\nSi el prospecto insiste en algo que no debes tratar, no lo trates: "
            "dile con calidez que el asesor lo ve directamente y sigue adelante.\n")


# Catálogo de datos a calificar. La clave la manda la pantalla (checkbox); aquí
# se traduce a la frase que entiende el modelo. El backend solo acepta claves de
# este diccionario, así nadie inyecta texto raro por esta vía.
CALIF_OPCIONES = {
    "forma_pago":  "si va a pagar con crédito o de contado",
    "presupuesto": "el presupuesto real que maneja",
    "enganche":    "cuánto trae de enganche",
    "zona":        "en qué zona o colonia busca",
    "tipo":        "qué tipo de inmueble quiere (casa, departamento, terreno…)",
    "recamaras":   "cuántas recámaras necesita",
    "urgencia":    "para cuándo lo necesita",
    "motivo":      "si es para vivir o para invertir",
    "credito_pre": "si ya está precalificado con algún banco",
    "da_a_cuenta": "si tiene una propiedad o algo que dar a cuenta",
}


def _calificacion_para_prompt(entren: dict) -> str:
    """Qué debe averiguar Recepción, armado con lo que el asesor palomeó. Si no
    palomeó nada, cae al set clásico para no bajar la calidad de siempre."""
    claves = entren.get("datos_calificar") or []
    frases = [CALIF_OPCIONES[k] for k in claves if k in CALIF_OPCIONES]
    if not frases:
        frases = [CALIF_OPCIONES["forma_pago"], CALIF_OPCIONES["presupuesto"],
                  CALIF_OPCIONES["urgencia"], "qué está buscando"]
    return "; ".join(frases)


def _saber_del_negocio(entren: dict) -> str:
    """Lo que hace a Recepción sonar como alguien que conoce el negocio:
    especialidad, meta de la plática, preguntas propias del asesor y su base de
    respuestas frecuentes. Todo opcional; lo vacío no aparece en el prompt."""
    bloques = []
    if (entren.get("especialidad") or "").strip():
        bloques.append(f"A qué se dedica el asesor: {entren['especialidad'].strip()}")
    if (entren.get("objetivo") or "").strip():
        bloques.append(f"Tu meta en cada plática: {entren['objetivo'].strip()}. "
                       "Llévala hacia ahí de forma natural, sin presionar.")
    extra = [(p or "").strip() for p in (entren.get("preguntas_extra") or []) if (p or "").strip()]
    if extra:
        lista = " ".join(f"«{p}»" for p in extra)
        bloques.append("Además de lo estándar, en algún momento natural pregunta: " + lista)
    pares = []
    for item in (entren.get("faq") or []):
        if isinstance(item, dict):
            q = (item.get("q") or "").strip()
            a = (item.get("a") or "").strip()
            if q and a:
                pares.append(f"  · Si preguntan algo como «{q}», contesta: {a}")
    if pares:
        bloques.append("Respuestas que el asesor ya te dio y debes usar tal cual "
                       "(no las inventes ni las cambies):\n" + "\n".join(pares))
    if not bloques:
        return ""
    reglas = "\n".join(f"- {b}" for b in bloques)
    return "\n\nLO QUE SABES DEL NEGOCIO:\n" + reglas + "\n"


# =============================================================================
# 4) RECEPCIÓN (la IA)  ->  Anthropic, responde y califica de una
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
                             agente: dict | None = None,
                             entren: dict | None = None) -> dict:
    agente = agente or {"nombre": "tu asesor inmobiliario", "zona": ""}
    entren = entren or dict(TRAINING_DEFAULTS)
    quien  = agente["nombre"]
    zona   = agente.get("zona") or ""
    ubica  = f" en {zona}" if zona else ""
    hoy    = _fmt_fecha_larga(_hora_local())

    contexto = property_ctx or (
        f"Atiendes prospectos de {quien}, asesor inmobiliario{ubica}. "
        "Si no sabes por qué propiedad escribe, pregúntale qué busca."
    )
    system = (
        f"Eres 'Recepción', el asistente de WhatsApp de {quien}, asesor inmobiliario{ubica}. "
        "Atiendes a un prospecto que escribió por un anuncio. Califícalo con calidez y rapidez, sin sonar "
        f"a robot ni a interrogatorio: averigua {_calificacion_para_prompt(entren)}; cuando haga sentido, "
        "ofrece agendar una visita con día y hora. Español "
        "mexicano, cálido y profesional, mensajes cortos de WhatsApp, sin emojis. "
        f"Hoy es {hoy}, úsalo para entender cuándo dice 'mañana', 'el sábado', etc.\n\n"
        f"Contexto: {contexto}\n"
        f"{_saber_del_negocio(entren)}"
        f"{_reglas_para_prompt(entren)}\n"
        "Cuando el prospecto pida ver opciones, o cuando ya sepas lo suficiente para mostrarle "
        "propiedades, NO inventes inmuebles ni des direcciones exactas: en 'accion' pide enviarle "
        "opciones con los filtros que tengas (los que no sepas, déjalos en null) y el sistema le manda "
        "propiedades REALES del catálogo del asesor. En 'reply' avísale en una línea que se las vas a "
        "compartir. Usa esto solo cuando de verdad toque mostrar propiedades; si sigues calificando, "
        "deja 'accion' en null.\n"
        "Cuando el prospecto acepte un día y una hora concretos para la visita, ponlo en 'accion' como "
        "agendar_visita con la fecha (YYYY-MM-DD) y la hora (HH:MM en 24h); el sistema le manda la "
        "invitación al calendario y le avisa al asesor. Si aún no hay día y hora firmes, no lo pongas.\n"
        "Responde ÚNICAMENTE con un JSON válido, sin texto antes ni después, así:\n"
        '{"reply":"el mensaje para el prospecto","temperatura":"Caliente|Tibio|Frío",'
        '"score":0-100,"presupuesto":"texto o null","forma_pago":"crédito|contado|por definir",'
        '"busca":"1 frase o null","listo_para_visita":true,"resumen":"1 frase para el agente",'
        '"accion":null}\n'
        "El campo 'accion' es null casi siempre. Cuando toque mostrar propiedades: "
        '{"tipo":"enviar_inmuebles","filtros":{"operacion":"venta|renta|null",'
        '"tipo":"casa|departamento|terreno u otro texto, o null","zona":"colonia o ciudad, o null",'
        '"precio_max":numero o null,"recamaras":numero o null}}. '
        "Cuando el prospecto ya aceptó día y hora: "
        '{"tipo":"agendar_visita","fecha":"YYYY-MM-DD","hora":"HH:MM","inmueble":"texto o null"}'
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


async def wa_send_text(phone_number_id: str, to: str, body: str,
                       token: str | None = None) -> dict:
    """Envía y REPORTA si se pudo. Devuelve siempre la misma forma:
        {"ok": bool, "message_id": str|None, "error": str|None, "code": int|None}

    Antes devolvía el JSON crudo de Meta y quien llamaba deducía el éxito de si
    venía o no un id. Un rechazo (p. ej. #131037, nombre visible sin aprobar)
    era indistinguible de un envío bueno, así que la bandeja guardaba mensajes
    que jamás salieron y /send contestaba 200 OK. Nunca más."""
    if not token:
        row = await resolve_number(phone_number_id)
        token = (row or {}).get("access_token") or WHATSAPP_TOKEN
    if not token:
        log.error("Sin token para phone_number_id=%s — no se envía", phone_number_id)
        return {"ok": False, "message_id": None, "code": None,
                "error": "No hay token de acceso para este número."}

    to = _normaliza_mx(to)
    url = f"{GRAPH_API}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(url, headers=headers, json=data)
            payload = r.json() if r.content else {}

            if r.status_code >= 400:
                err  = (payload.get("error") or {})
                code = err.get("code")
                msg  = err.get("message") or r.text[:200]
                log.error("WhatsApp send error %s (code=%s) a %s: %s",
                          r.status_code, code, to, msg)
                return {"ok": False, "message_id": None, "code": code,
                        "error": _error_legible(code, msg)}

            mid = (payload.get("messages") or [{}])[0].get("id")
            if not mid:
                log.error("Meta respondió 200 sin message id: %s", json.dumps(payload)[:300])
                return {"ok": False, "message_id": None, "code": None,
                        "error": "Meta aceptó la petición pero no devolvió un id de mensaje."}

            log.info("WhatsApp enviado a %s (%s)", to, mid)
            return {"ok": True, "message_id": mid, "error": None, "code": None}
    except Exception as e:
        log.exception("Error enviando WhatsApp a %s: %s", to, e)
        return {"ok": False, "message_id": None, "code": None,
                "error": "No se pudo contactar a WhatsApp. Intenta de nuevo."}


async def wa_send_image(phone_number_id: str, to: str, image_url: str,
                        caption: str | None = None, token: str | None = None) -> dict:
    """Manda una imagen por su URL pública (así son las fotos del bucket) con pie
    de foto opcional. Misma forma de retorno que wa_send_text para que quien
    llama trate el éxito/fracaso igual."""
    if not token:
        row = await resolve_number(phone_number_id)
        token = (row or {}).get("access_token") or WHATSAPP_TOKEN
    if not token:
        log.error("Sin token para phone_number_id=%s — no se envía imagen", phone_number_id)
        return {"ok": False, "message_id": None, "code": None,
                "error": "No hay token de acceso para este número."}

    to = _normaliza_mx(to)
    url = f"{GRAPH_API}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    img = {"link": image_url}
    if caption:
        img["caption"] = caption[:1024]
    data = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": img}
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post(url, headers=headers, json=data)
            payload = r.json() if r.content else {}
            if r.status_code >= 400:
                err  = (payload.get("error") or {})
                code = err.get("code")
                msg  = err.get("message") or r.text[:200]
                log.error("WhatsApp image error %s (code=%s) a %s: %s",
                          r.status_code, code, to, msg)
                return {"ok": False, "message_id": None, "code": code,
                        "error": _error_legible(code, msg)}
            mid = (payload.get("messages") or [{}])[0].get("id")
            if not mid:
                log.error("Meta 200 sin id en imagen: %s", json.dumps(payload)[:300])
                return {"ok": False, "message_id": None, "code": None,
                        "error": "Meta aceptó la imagen pero no devolvió un id."}
            return {"ok": True, "message_id": mid, "error": None, "code": None}
    except Exception as e:
        log.exception("Error enviando imagen a %s: %s", to, e)
        return {"ok": False, "message_id": None, "code": None,
                "error": "No se pudo contactar a WhatsApp."}


# =============================================================================
# 4b) ACCIONES DE RECEPCIÓN  ->  cosas grandes que la IA puede pedir hacer
# =============================================================================
# La IA NO inventa inmuebles ni los saca de la nada: en su JSON pide una acción y
# el backend la ejecuta contra Supabase con datos REALES. Mismo principio que
# Broq: nunca afirmar inventario sin confirmarlo en la base.
def _money_mx(v) -> str:
    try:
        return "$" + f"{float(v):,.0f}"
    except Exception:
        return str(v or "")


# Estatus que NO se le mandan a un prospecto (ya no están disponibles).
_ESTATUS_FUERA = {"vendido", "vendida", "rentado", "rentada", "baja",
                  "inactivo", "inactiva", "no disponible", "cerrado", "pausado"}


async def _buscar_inmuebles_para_enviar(user_id: str, filtros: dict) -> list:
    """Hasta 3 propiedades reales del asesor que encajen con lo que pidió el
    prospecto. Si un filtro no viene, no se aplica. Se descartan las que ya no
    están disponibles. Devuelve [] solo si de verdad no hay coincidencias."""
    sel = ("id,titulo,tipo,operacion,precio,moneda,colonia,ciudad,calle,"
           "recamaras,banos,estacionamientos,m2_construccion,m2_terreno,estatus,fotos")
    params = {"user_id": f"eq.{user_id}", "select": sel,
              "order": "updated_at.desc", "limit": "12"}

    op = str(filtros.get("operacion") or "").strip().lower()
    if op in ("venta", "renta"):
        params["operacion"] = f"eq.{op}"
    tipo = str(filtros.get("tipo") or "").strip().lower()
    if tipo:
        params["tipo"] = f"ilike.*{tipo}*"
    zona = str(filtros.get("zona") or "").strip()
    if zona:
        safe = zona.replace(",", " ").replace("(", " ").replace(")", " ")
        params["or"] = (f"(titulo.ilike.*{safe}*,colonia.ilike.*{safe}*,"
                        f"calle.ilike.*{safe}*,ciudad.ilike.*{safe}*)")
    pmax = filtros.get("precio_max")
    if pmax:
        try:
            params["precio"] = f"lte.{int(float(pmax))}"
        except Exception:
            pass
    rec = filtros.get("recamaras")
    if rec:
        try:
            params["recamaras"] = f"gte.{int(rec)}"
        except Exception:
            pass

    rows = await sb_get("propiedades", params)
    buenas = [p for p in (rows or [])
              if str(p.get("estatus") or "").strip().lower() not in _ESTATUS_FUERA]
    return buenas[:3]


def _tarjeta_inmueble(p: dict) -> str:
    """Pie de foto corto y claro para WhatsApp. Sin direcciones exactas: colonia
    y ciudad bastan hasta que haya cita."""
    lineas = [p.get("titulo") or p.get("tipo") or "Propiedad"]
    ubic = " · ".join(x for x in [p.get("colonia"), p.get("ciudad")] if x)
    if ubic:
        lineas.append(ubic)
    if p.get("precio"):
        op = f" ({p['operacion']})" if p.get("operacion") else ""
        lineas.append(f"{_money_mx(p['precio'])} {p.get('moneda') or 'MXN'}{op}")
    det = []
    if p.get("recamaras"):        det.append(f"{p['recamaras']} rec")
    if p.get("banos"):            det.append(f"{p['banos']} baños")
    if p.get("estacionamientos"): det.append(f"{p['estacionamientos']} autos")
    if p.get("m2_construccion"):  det.append(f"{p['m2_construccion']} m² const")
    if det:
        lineas.append(" · ".join(det))
    return "\n".join(lineas)[:1024]


async def _enviar_inmuebles(user_id, phone_number_id, to, filtros, contact,
                            conversation_id, token, agente_nombre) -> int:
    """Manda al prospecto hasta 3 tarjetas de inmueble (foto + datos) y las guarda
    en el hilo como mensajes de Recepción. Si no hay coincidencias, manda un texto
    honesto y le avisa al asesor —nunca inventa ni deja al prospecto colgado."""
    props = await _buscar_inmuebles_para_enviar(user_id, filtros or {})
    if not props:
        txt = ("Justo ahora no tengo algo que encaje exacto con eso, pero deja lo "
               f"confirmo con {agente_nombre} y te comparto opciones enseguida.")
        sent = await wa_send_text(phone_number_id, to, txt, token=token)
        if sent["ok"]:
            await store_message(user_id, contact["id"], conversation_id,
                                sent["message_id"] or f"local-noinv-{to}",
                                "out", "ai", txt, status="sent")
        await avisar_al_agente(user_id, contact, conversation_id,
                               "Recepción quiso mandar inmuebles y no halló coincidencias "
                               "con lo que pidió el prospecto. Échale un ojo al chat.")
        return 0

    enviados = 0
    for p in props:
        caption = _tarjeta_inmueble(p)
        fotos = p.get("fotos") or []
        foto = None
        if isinstance(fotos, list):
            foto = next((f for f in fotos if isinstance(f, str) and f.strip()), None)
        if foto:
            sent = await wa_send_image(phone_number_id, to, foto, caption, token=token)
            # Si la foto no pasó (URL pesada, formato que Meta no acepta), no
            # dejamos al prospecto sin la opción: la mandamos en texto.
            if not sent["ok"]:
                sent = await wa_send_text(phone_number_id, to, caption, token=token)
        else:
            sent = await wa_send_text(phone_number_id, to, caption, token=token)
        if sent["ok"]:
            enviados += 1
            await store_message(user_id, contact["id"], conversation_id,
                                sent["message_id"] or f"local-inm-{p.get('id')}",
                                "out", "ai", "[Inmueble] " + caption, status="sent")
        else:
            log.warning("No se pudo enviar inmueble %s: %s", p.get("id"), sent.get("error"))
    return enviados


# URL pública del backend, para la invitación .ics que el prospecto abre desde
# WhatsApp. Se puede sobreescribir por env si algún día cambia el dominio.
API_PUBLIC_BASE = os.environ.get("API_PUBLIC_BASE", "https://api.broquer.app")

_DIAS  = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fmt_fecha_larga(dt) -> str:
    """'sábado 26 de julio, 5:00 PM' — para confirmarle al prospecto en claro."""
    h = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return (f"{_DIAS[dt.weekday()]} {dt.day} de {_MESES[dt.month - 1]}, "
            f"{h}:{dt.minute:02d} {ampm}")


def _parse_cita(fecha, hora):
    """'YYYY-MM-DD' + 'HH:MM' -> datetime con tz de México. None si no es válida
    o si ya pasó: no agendamos en el pasado."""
    try:
        y, m, d = [int(x) for x in str(fecha).split("-")]
        hh, mm = _hhmm(hora, "10:00")
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("America/Mexico_City")
        except Exception:
            tz = timezone(timedelta(hours=-6))
        dt = datetime(y, m, d, hh, mm, tzinfo=tz)
        if dt < datetime.now(tz) - timedelta(minutes=1):
            return None
        return dt
    except Exception:
        return None


def _ics_de_cita(cita: dict, agente_nombre: str) -> str:
    """Genera el .ics (VEVENT en UTC) que abre el prospecto con un toque. Sirve
    igual en Calendario de Apple, Google Calendar y Outlook."""
    def _z(dt_utc):
        return dt_utc.strftime("%Y%m%dT%H%M%SZ")

    starts = cita.get("starts_at")
    if isinstance(starts, str):
        try:
            dt = datetime.fromisoformat(starts.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(timezone.utc)
    else:
        dt = starts or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    fin_utc = dt_utc + timedelta(minutes=int(cita.get("duracion_min") or 60))

    inm = (cita.get("inmueble") or "").strip()
    titulo = f"Visita: {inm}" if inm else "Visita de propiedad"
    desc = f"Cita agendada con {agente_nombre} por WhatsApp."

    def esc(t):
        return (str(t or "").replace("\\", "\\\\").replace(",", "\\,")
                .replace(";", "\\;").replace("\n", "\\n"))

    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Broquer//Recepcion//ES",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "BEGIN:VEVENT",
        f"UID:{cita.get('id')}@broquer.app",
        f"DTSTAMP:{_z(datetime.now(timezone.utc))}",
        f"DTSTART:{_z(dt_utc)}", f"DTEND:{_z(fin_utc)}",
        f"SUMMARY:{esc(titulo)}", f"DESCRIPTION:{esc(desc)}",
        "END:VEVENT", "END:VCALENDAR",
    ]) + "\r\n"


async def wa_send_document(phone_number_id: str, to: str, doc_url: str, filename: str,
                           caption: str | None = None, token: str | None = None) -> dict:
    """Manda un documento por su URL pública (la usamos para el .ics de la cita).
    Misma forma de retorno que wa_send_text."""
    if not token:
        row = await resolve_number(phone_number_id)
        token = (row or {}).get("access_token") or WHATSAPP_TOKEN
    if not token:
        log.error("Sin token para phone_number_id=%s — no se envía documento", phone_number_id)
        return {"ok": False, "message_id": None, "code": None,
                "error": "No hay token de acceso para este número."}

    to = _normaliza_mx(to)
    url = f"{GRAPH_API}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    doc = {"link": doc_url, "filename": filename}
    if caption:
        doc["caption"] = caption[:1024]
    data = {"messaging_product": "whatsapp", "to": to, "type": "document", "document": doc}
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post(url, headers=headers, json=data)
            payload = r.json() if r.content else {}
            if r.status_code >= 400:
                err  = (payload.get("error") or {})
                code = err.get("code")
                msg  = err.get("message") or r.text[:200]
                log.error("WhatsApp doc error %s (code=%s) a %s: %s",
                          r.status_code, code, to, msg)
                return {"ok": False, "message_id": None, "code": code,
                        "error": _error_legible(code, msg)}
            mid = (payload.get("messages") or [{}])[0].get("id")
            return {"ok": bool(mid), "message_id": mid,
                    "error": None if mid else "Meta no devolvió id de documento.", "code": None}
    except Exception as e:
        log.exception("Error enviando documento a %s: %s", to, e)
        return {"ok": False, "message_id": None, "code": None,
                "error": "No se pudo contactar a WhatsApp."}


async def _accion_agendar_visita(user_id, phone_number_id, to, accion, contact,
                                 conversation_id, token, agente_nombre) -> bool:
    """Guarda la cita, la marca en el CRM, le manda al prospecto la invitación
    universal (.ics) y le avisa al asesor. True si se agendó."""
    dt = _parse_cita(accion.get("fecha"), accion.get("hora"))
    if not dt:
        # La IA quiso agendar pero la fecha/hora no sirve: que el asesor lo cierre
        # a mano en vez de inventar una cita falsa.
        await avisar_al_agente(user_id, contact, conversation_id,
                               "El prospecto quiere agendar una visita. Ciérrale día y hora tú.")
        return False

    inmueble = (accion.get("inmueble") or "").strip()[:200] or None
    dt_utc = dt.astimezone(timezone.utc)
    creado = await sb_post("wa_citas", {
        "user_id": user_id, "contact_id": contact["id"],
        "conversation_id": conversation_id, "inmueble": inmueble,
        "starts_at": dt_utc.isoformat(), "duracion_min": 60,
    })
    if not creado:
        log.error("No se pudo guardar la cita de %s", to)
        await avisar_al_agente(user_id, contact, conversation_id,
                               "El prospecto aceptó una visita pero no pude guardarla. Coordínala tú.")
        return False
    cita = creado[0]

    # Marca en el CRM: etapa Cita + próxima cita para el expediente.
    await sb_patch("wa_contacts", {"id": f"eq.{contact['id']}"},
                   {"etapa": "Cita", "cita_at": dt_utc.isoformat(), "updated_at": _now()})

    cuando = _fmt_fecha_larga(dt)
    lugar  = f" para ver {inmueble}" if inmueble else ""
    ics_url = f"{API_PUBLIC_BASE}/whatsapp/cita/{cita['id']}.ics"
    caption = (f"Tu visita quedó el {cuando}{lugar}. "
               "Toca el archivo para agregarla a tu calendario.")
    sent = await wa_send_document(phone_number_id, to, ics_url, "cita-broquer.ics",
                                  caption, token=token)
    if sent["ok"]:
        await store_message(user_id, contact["id"], conversation_id,
                            sent["message_id"] or f"local-cita-{cita['id']}",
                            "out", "ai", f"[Cita] {cuando}{lugar}", status="sent")
    else:
        # Si el documento no salió, al menos confirma en texto para no dejarlo en el aire.
        txt = f"Tu visita quedó el {cuando}{lugar}. ¡Ahí te esperamos!"
        s2 = await wa_send_text(phone_number_id, to, txt, token=token)
        if s2["ok"]:
            await store_message(user_id, contact["id"], conversation_id,
                                s2["message_id"] or f"local-cita-{cita['id']}",
                                "out", "ai", f"[Cita] {cuando}{lugar}", status="sent")

    await avisar_al_agente(user_id, contact, conversation_id, f"Nueva cita: {cuando}{lugar}.")
    return True


def _error_legible(code, msg: str) -> str:
    """Traduce los rechazos más comunes de Meta a algo que el agente entienda
    y pueda accionar. Si no lo conocemos, se pasa el mensaje de Meta tal cual."""
    conocidos = {
        131037: ("Tu número aún no tiene el nombre visible aprobado por Meta. "
                 "Ve a WhatsApp Manager y mándalo a aprobación: hasta entonces "
                 "puedes recibir mensajes, pero no responder."),
        131047: ("Pasaron más de 24 horas desde el último mensaje del prospecto. "
                 "Para reabrir la conversación hay que enviar una plantilla."),
        131026: "El número del destinatario no tiene WhatsApp o no puede recibir mensajes.",
        131031: "Meta bloqueó tu cuenta de WhatsApp. Revisa WhatsApp Manager.",
        190:    "La conexión con WhatsApp caducó. Vuelve a conectar tu número.",
        131049: "Meta limitó el envío a este usuario para cuidar la experiencia.",
        130429: "Estás enviando demasiado rápido. Espera un momento.",
    }
    return conocidos.get(code, msg)


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

    if not sent["ok"]:
        # NO se guarda el mensaje ni se apaga la IA: el prospecto no recibió nada,
        # así que Recepción debe seguir a cargo. Antes esto devolvía 200 OK, el
        # mensaje aparecía en la bandeja y la IA quedaba apagada — el peor caso:
        # el agente creía haber contestado y nadie estaba atendiendo al lead.
        raise HTTPException(status_code=502, detail=sent["error"])

    await store_message(user_id, conv["contact_id"], conv["id"],
                        sent["message_id"], "out", "agent", req.body, status="sent")
    # el humano contestó -> apagamos la IA en esta conversación
    await sb_patch("wa_conversations", {"id": f"eq.{conv['id']}"}, {"ai_enabled": False})
    return {"ok": True, "wa_message_id": sent["message_id"]}


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


def _norm10(num: str) -> str:
    """Últimos 10 dígitos. Es la llave con la que se cruza WhatsApp contra
    Contactos: aguanta +52, el 1 de móvil, 044/045, espacios y guiones.
    Regla mexicana — revisar cuando entre Colombia."""
    d = "".join(ch for ch in str(num or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else ""


def _nuevo_contacto_id() -> str:
    """contactos.id NO se autogenera: lo arma el frontend como 'c_' + Date.now()
    (contactos.html:1380). El backend debe seguir la misma convención o el
    insert truena por not-null."""
    return "c_" + str(int(datetime.now(timezone.utc).timestamp() * 1000))


async def vincular_contacto(user_id: str, wa_id: str, nombre: str | None) -> str | None:
    """Devuelve el id de contactos para este número de WhatsApp.
    Si ya existe (por teléfono o por el campo wa), lo reutiliza y NO lo pisa:
    los datos que el agente capturó a mano mandan sobre lo que diga WhatsApp.
    Si no existe, lo crea marcado como potencial y con fuente WhatsApp."""
    norm = _norm10(wa_id)
    if not norm:
        return None

    try:
        # Busca en el universo de ESE agente, contra los dos campos de teléfono
        rows = await sb_get("contactos", {
            "user_id": f"eq.{user_id}",
            "or":      f"(tel_norm.eq.{norm},wa_norm.eq.{norm})",
            "select":  "id",
            "order":   "updated_at.desc",
            "limit":   "1",
        })
        if isinstance(rows, list) and rows:
            return rows[0]["id"]

        creado = await sb_post("contactos", {
            "id":           _nuevo_contacto_id(),
            "user_id":      user_id,
            "nombre":       (nombre or "").strip() or f"WhatsApp {norm[-4:]}",
            "telefono":     norm,
            "wa":           norm,
            "tipo":         "prospecto",
            "es_potencial": True,
            "fuente":       "WhatsApp",
            "notas":        "Creado automáticamente por Recepción al recibir el primer mensaje.",
        })
        # sb_post devuelve r.json() tal cual: si PostgREST rechaza, es un DICT de
        # error, no una lista. Sin este chequeo el fallo real quedaba enterrado
        # bajo un KeyError genérico y el log no servía para nada.
        if isinstance(creado, dict):
            log.error("Supabase rechazó el contacto para %s: %s", wa_id, json.dumps(creado)[:400])
            return None
        if isinstance(creado, list) and creado:
            log.info("Contacto creado desde WhatsApp: %s -> %s", norm, creado[0].get("id"))
            return creado[0]["id"]
        log.error("Supabase no devolvió el contacto creado para %s: %r", wa_id, creado)
    except Exception as e:
        # Nunca tumbar la conversación por un fallo del CRM: el lead se atiende
        # igual y queda en wa_contacts; el enlace se puede reparar después.
        log.exception("No se pudo vincular contacto para %s: %s", wa_id, e)
    return None


async def upsert_contact(user_id, wa_id, nombre):
    rows = await sb_get("wa_contacts",
                        {"user_id": f"eq.{user_id}", "wa_id": f"eq.{wa_id}", "limit": "1"})
    if rows:
        contact = rows[0]
        patch = {}
        if nombre and not contact.get("nombre"):
            patch["nombre"] = nombre
        # Repara el enlace si falta (contacto creado a mano después, o backfill fallido)
        if not contact.get("contacto_id"):
            cid = await vincular_contacto(user_id, wa_id, nombre or contact.get("nombre"))
            if cid:
                patch["contacto_id"] = cid
        if patch:
            await sb_patch("wa_contacts", {"id": f"eq.{contact['id']}"}, patch)
            contact.update(patch)
        return contact

    contacto_id = await vincular_contacto(user_id, wa_id, nombre)
    created = await sb_post("wa_contacts",
                            {"user_id": user_id, "wa_id": wa_id, "nombre": nombre,
                             "contacto_id": contacto_id,
                             "temperatura": "Nuevo", "score": 0, "etapa": "Nuevo"})
    if created:
        return created[0]

    # El INSERT no devolvió fila. Casi siempre es una carrera: el mismo lead nuevo
    # mandó varios mensajes de golpe y otro webhook ya creó el contacto (chocamos
    # en unique(user_id, wa_id)). Releemos por esa llave: si ya existe, lo usamos.
    # Así el chat NUNCA se queda sin contacto y sus mensajes no se pierden.
    rows = await sb_get("wa_contacts",
                        {"user_id": f"eq.{user_id}", "wa_id": f"eq.{wa_id}", "limit": "1"})
    if rows:
        return rows[0]
    log.error("wa_contacts: no se pudo crear ni releer el contacto de %s (user %s)",
              wa_id, user_id)
    return {"id": None}


async def get_or_create_conversation(user_id, contact, referral, phone_number_id,
                                     ia_global: bool = True):
    rows = await sb_get("wa_conversations", {"contact_id": f"eq.{contact['id']}", "limit": "1"})
    if rows:
        return rows[0]
    property_ctx = None
    if referral:
        headline = referral.get("headline", "")
        bodytext = referral.get("body", "")
        property_ctx = f"El prospecto escribió por el anuncio: '{headline}'. {bodytext}".strip()
    # ai_enabled ya NO es True hardcodeado: nacía encendida aunque el agente
    # tuviera Recepción apagada, y ese era el agujero por el que la IA seguía
    # contestando con el switch en off.
    created = await sb_post("wa_conversations",
                            {"user_id": user_id, "contact_id": contact["id"],
                             "phone_number_id": phone_number_id,
                             "ai_enabled": bool(ia_global),
                             "ai_msg_count": 0,
                             "property_ctx": property_ctx})
    if created:
        return created[0]

    # Misma carrera que en contactos: unique(contact_id). Si otro webhook ya creó
    # la conversación, la releemos y seguimos con ella en vez de devolver id nulo
    # (que dejaría todos los mensajes de este chat huérfanos y sin guardar).
    rows = await sb_get("wa_conversations", {"contact_id": f"eq.{contact['id']}", "limit": "1"})
    if rows:
        return rows[0]
    log.error("wa_conversations: no se pudo crear ni releer la conversación de contacto %s",
              contact["id"])
    return {"id": None, "ai_enabled": bool(ia_global), "ai_msg_count": 0}


async def sumar_msg_ia(conversation_id, actual):
    """Lleva la cuenta de cuántas veces habló la IA en este chat. Alimenta
    max_mensajes_ia sin tener que contar filas de wa_messages en cada webhook."""
    try:
        await sb_patch("wa_conversations", {"id": f"eq.{conversation_id}"},
                       {"ai_msg_count": int(actual or 0) + 1, "updated_at": _now()})
    except Exception as e:
        log.warning("No se pudo sumar ai_msg_count en %s: %s", conversation_id, e)


async def store_message(user_id, contact_id, conversation_id, wa_message_id, direction, sender, body,
                        status: str | None = None):
    """status: 'sent' | 'failed' | None (entrantes). La columna ya existía en el
    esquema pero nadie la escribía, así que un mensaje rechazado por Meta se veía
    idéntico a uno entregado."""
    # Si el contacto o la conversación no se pudieron crear/releer arriba, sus ids
    # llegan en None. Insertar así truena por NOT NULL y, peor, deja el mensaje
    # perdido en silencio. Mejor abortar claro y dejarlo en el log.
    if not conversation_id or not contact_id:
        log.error("store_message abortado por ids nulos (conv=%s contact=%s sender=%s)",
                  conversation_id, contact_id, sender)
        return

    fila = {"user_id": user_id, "contact_id": contact_id, "conversation_id": conversation_id,
            "wa_message_id": wa_message_id, "direction": direction, "sender": sender, "body": body}
    if status:
        fila["status"] = status
    # return=representation (no minimal) para poder VERIFICAR que la fila aterrizó.
    guardado = await sb_post("wa_messages", fila)
    if not guardado and wa_message_id and not str(wa_message_id).startswith("local-"):
        # sb_post ya reintentó ante timeouts. Si aun así no hubo fila, puede ser
        # un duplicado legítimo (Meta reentregó y ya estaba) o una pérdida real.
        # Releemos por wa_message_id: si NO está, es que se perdió de verdad y hay
        # que verlo en el log — es justo el "no se actualiza la conversación".
        ya = await sb_get("wa_messages",
                          {"wa_message_id": f"eq.{wa_message_id}", "select": "id", "limit": "1"})
        if not ya:
            log.error("wa_messages NO guardado (mensaje perdido): conv=%s sender=%s wamid=%s",
                      conversation_id, sender, wa_message_id)
    await sb_patch("wa_conversations", {"id": f"eq.{conversation_id}"}, {"last_message_at": _now()})


async def sumar_no_leido(conversation_id) -> int:
    """Sube en 1 el contador de mensajes sin leer de la conversación y lo
    regresa. La bandeja lo baja a 0 cuando el agente abre el chat.
    Postgres no tiene 'incrementa' por REST, así que se lee y se escribe."""
    try:
        filas = await sb_get("wa_conversations",
                             {"id": f"eq.{conversation_id}", "select": "unread_count", "limit": "1"})
        actual = int((filas[0] or {}).get("unread_count") or 0) if filas else 0
        nuevo = actual + 1
        await sb_patch("wa_conversations", {"id": f"eq.{conversation_id}"}, {"unread_count": nuevo})
        return nuevo
    except Exception as e:
        log.warning("No se pudo actualizar unread_count: %s", e)
        return 0


async def total_no_leidos(user_id) -> int:
    """Suma de todos los chats sin leer del agente: es el número que va en el
    globito rojo del ícono de la app."""
    try:
        filas = await sb_get("wa_conversations", {"user_id": f"eq.{user_id}", "select": "unread_count"})
        return sum(int(f.get("unread_count") or 0) for f in (filas or []))
    except Exception:
        return 0


async def avisar_al_agente(user_id, contact, conversation_id, texto):
    """Notificación push al iPhone del agente. Envuelto en try porque un aviso
    que no sale JAMÁS debe tumbar el webhook de Meta (Meta reintentaría y se
    duplicarían mensajes)."""
    try:
        nombre = (contact or {}).get("nombre") or _norm10((contact or {}).get("wa_id", "")) or "Nuevo mensaje"
        badge = await total_no_leidos(user_id)
        await avisar_mensaje_whatsapp(user_id, nombre, texto, str(conversation_id), badge=badge)
    except Exception as e:
        log.warning("Push no enviado: %s", e)


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


async def ai_sigue_encendida(conversation_id, user_id: str | None = None) -> bool:
    """Se relee justo antes de mandar porque el modelo tarda unos segundos y en
    ese hueco el agente pudo contestar desde su cel o apagar el switch global.
    Revisa las dos cosas: si cualquiera está en off, la IA no manda."""
    rows = await sb_get("wa_conversations",
                        {"id": f"eq.{conversation_id}", "select": "ai_enabled", "limit": "1"})
    if not rows or not rows[0].get("ai_enabled", True):
        return False
    if user_id:
        nums = await sb_get("wa_numbers", {"user_id": f"eq.{user_id}",
                                           "select": "ia_enabled", "limit": "1"})
        if nums and nums[0].get("ia_enabled", True) is False:
            return False
    return True


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
    """Enciende o apaga Recepción para todo. Palabra final del agente.

    Ya NO propaga a wa_conversations. La propagación era la causa de dos bugs:
    apagar solo alcanzaba a las conversaciones existentes (un lead nuevo nacía
    con la IA encendida), y prender revivía la IA en chats que el agente había
    tomado a mano. Ahora el webhook evalúa ia_global AND conv.ai_enabled, así
    que cada flag conserva su significado y ninguno pisa al otro.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")
    await sb_patch("wa_numbers", {"user_id": f"eq.{user_id}"}, {
        "ia_enabled": req.ia_enabled,
        "updated_at": _now(),
    })
    return {"ok": True, "ia_enabled": req.ia_enabled}


# ── /whatsapp/training ────────────────────────────────────────────────────────
class TrainingReq(BaseModel):
    tono: str | None = None
    primer_mensaje: str | None = None
    puede: str | None = None
    debe: str | None = None
    no_debe: str | None = None
    horario_activo: bool = False
    hora_inicio: str = "08:00"
    hora_fin: str = "21:00"
    fuera_horario_msg: str | None = None
    max_mensajes_ia: int = 0
    escalar_palabras: list[str] = []
    activo: bool = True
    especialidad: str | None = None
    objetivo: str | None = None
    datos_calificar: list[str] = []
    preguntas_extra: list[str] = []
    faq: list[dict] = []


@router.get("/training")
async def wa_training_get(request: Request):
    """Reglas del agente. Si nunca guardó, devuelve los defaults."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")
    return await entrenamiento(user_id)


@router.put("/training")
async def wa_training_put(req: TrainingReq, request: Request):
    """Guarda las reglas. Upsert por user_id (PK), sin fila duplicada posible."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    hi, mi = _hhmm(req.hora_inicio, "08:00")
    hf, mf = _hhmm(req.hora_fin, "21:00")
    palabras = [p.strip() for p in (req.escalar_palabras or []) if (p or "").strip()][:20]

    # Solo claves válidas del catálogo; nada de texto libre entra por aquí.
    calif = [k for k in (req.datos_calificar or []) if k in CALIF_OPCIONES][:12]
    extra = [(p or "").strip()[:160] for p in (req.preguntas_extra or []) if (p or "").strip()][:5]
    faq = []
    for item in (req.faq or [])[:20]:
        if isinstance(item, dict):
            q = (item.get("q") or "").strip()[:160]
            a = (item.get("a") or "").strip()[:600]
            if q and a:
                faq.append({"q": q, "a": a})

    fila = {
        "user_id":           user_id,
        "tono":              (req.tono or "").strip()[:400] or None,
        "primer_mensaje":    (req.primer_mensaje or "").strip()[:600] or None,
        "puede":             (req.puede or "").strip()[:1500] or None,
        "debe":              (req.debe or "").strip()[:1500] or None,
        "no_debe":           (req.no_debe or "").strip()[:1500] or None,
        "horario_activo":    bool(req.horario_activo),
        "hora_inicio":       f"{hi:02d}:{mi:02d}",
        "hora_fin":          f"{hf:02d}:{mf:02d}",
        "fuera_horario_msg": (req.fuera_horario_msg or "").strip()[:600] or None,
        "max_mensajes_ia":   max(0, min(int(req.max_mensajes_ia or 0), 50)),
        "escalar_palabras":  palabras,
        "activo":            bool(req.activo),
        "especialidad":      (req.especialidad or "").strip()[:400] or None,
        "objetivo":          (req.objetivo or "").strip()[:300] or None,
        "datos_calificar":   calif,
        "preguntas_extra":   extra,
        "faq":               faq,
        "updated_at":        _now(),
    }
    await sb_post("wa_training", fila,
                  prefer="resolution=merge-duplicates,return=representation")
    return await entrenamiento(user_id)


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


# =============================================================================
# 7) INVITACIÓN DE CITA (.ics)  ->  la abre el prospecto desde WhatsApp
# =============================================================================
@router.get("/cita/{cita_id}.ics")
async def descargar_cita_ics(cita_id: str):
    """Sirve la invitación .ics de una cita. Es público a propósito: WhatsApp la
    descarga sin credenciales y el prospecto la abre con un toque. El id es un
    uuid al azar y el archivo solo trae día, hora y título —nada sensible."""
    rows = await sb_get("wa_citas", {"id": f"eq.{cita_id}", "select": "*", "limit": "1"})
    if not rows:
        return Response(status_code=404, content="Cita no encontrada", media_type="text/plain")
    cita = rows[0]
    agente = await perfil_agente(cita.get("user_id"))
    ics = _ics_de_cita(cita, agente.get("nombre") or "tu asesor")
    return Response(content=ics, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="cita-broquer.ics"'})
