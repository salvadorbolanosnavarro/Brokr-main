# ──────────────────────────────────────────────────────────────────────────
# routers/firmas.py · Broquer — Firma electrónica
# ──────────────────────────────────────────────────────────────────────────
# Mandar un contrato a firmar, recolectar las firmas de las partes y devolver
# un PDF con su constancia. Todo vive aquí.
#
# POR QUÉ ESTÁ AQUÍ Y NO EN main.py
#   Es autónomo (lee sus propias env vars) y se activa con 2 líneas en main.py,
#   igual que routers/cumplimiento.py. main.py casi no se toca.
#
# QUIÉN FIRMA
#   Las partes del contrato: promitente vendedor y comprador, arrendador y
#   arrendatario, fiador, cónyuge, copropietarios. NO el agente. El agente es
#   intermediario, no parte, y meterlo como firmante o como testigo solo lo
#   expone si las partes se pelean. Solo aparece cuando el contrato es suyo
#   (exclusiva, convenio entre asesores) y entonces entra como un firmante más.
#
#   Los firmantes NO son usuarios de Broquer. No tienen cuenta, no se registran,
#   firman una vez y no vuelven. Por eso todo el flujo público va por una liga
#   con token y cero fricción: si les pedimos crear contraseña, no firman.
#
# LA REGLA DE ORO DE ESTE ARCHIVO
#   El PDF original no se modifica NUNCA. Se guarda tal cual llegó, se le saca
#   el SHA-256 antes de mandarlo a firmar, y ese hash es el que aparece en la
#   constancia. El entregable final es ese mismo archivo, byte por byte, con
#   las hojas de constancia anexadas al final. Así "lo que leyeron" y "lo que
#   se guardó" son demostrablemente el mismo documento.
#
#   Corolario: aquí no se estampa el garabato encima del contrato. Se ve bonito
#   pero obliga a reescribir el archivo, y un archivo reescrito ya no coincide
#   con el hash de lo que la persona tenía enfrente. Las firmas viven en la
#   constancia.
#
# LO QUE ESTE MÓDULO NO HACE (todavía)
#   · No emite constancia de conservación NOM-151. Eso lo emite un PSC
#     acreditado por la Secretaría de Economía; no se puede autoemitir. Las
#     columnas nom151_* ya existen en la tabla: cuando se contrate el PSC es
#     un POST del hash después de la última firma, sin rediseñar nada.
#   · No usa e.firma del SAT. Se descartó a propósito: el comprador promedio
#     no la trae vigente y exigirla mata la conversión.
#   · No valida biométricamente la identidad. El nivel de identidad que da
#     este módulo es: control del teléfono o del correo (código de un solo
#     uso) + identificación oficial en archivo cuando el agente la exige.
#
# Depende de: migracion-firmas.sql ya corrido, y de pypdf en requirements.txt.
#
# Conectar en main.py:
#   from routers.firmas import router as firmas_router
#   app.include_router(firmas_router)
# ──────────────────────────────────────────────────────────────────────────

import os
import re
import io
import json
import html
import hashlib
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple

import httpx
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

router = APIRouter(prefix="/firmas", tags=["firmas"])
log = logging.getLogger("broquer.firmas")

# ── Config (mismas env vars que main.py) ──────────────────────────────────
SUPABASE_URL         = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY         = os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY
APP_URL              = os.getenv("APP_URL", "https://broquer.app").rstrip("/")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM    = os.getenv("RESEND_FROM", "Broquer <hola@broquer.app>")

# Plantilla de WhatsApp categoría AUTHENTICATION ya aprobada por Meta, si el
# agente tiene una. Sin ella, a un número que nunca nos ha escrito no le llega
# nada por WhatsApp (ventana de 24h cerrada) y el código se va por correo.
WA_PLANTILLA_OTP = os.getenv("WA_PLANTILLA_OTP", "")

BUCKET = "firmas"

# Vigencia por defecto de la invitación a firmar.
VIGENCIA_DIAS = 30

# El código de verificación. Corto de vida a propósito: es la prueba de que
# quien firmó tenía el teléfono en la mano en ese momento, no la semana pasada.
OTP_DIGITOS   = 6
OTP_MINUTOS   = 10
OTP_INTENTOS  = 5

# Cuánto dura una liga firmada para ver un archivo. El contrato lo tiene que
# poder leer con calma; la identificación oficial, no tanto.
FIRMA_SEGUNDOS     = 900
FIRMA_SEGUNDOS_INE = 300

MAX_PDF_BYTES   = 20 * 1024 * 1024
MAX_IMG_BYTES   = 8 * 1024 * 1024
MAX_TRAZO_BYTES = 1 * 1024 * 1024

MIMES_IMG = {"image/jpeg", "image/png", "image/webp", "image/heic"}

# ── Vocabulario del módulo ────────────────────────────────────────────────
TIPOS = {
    "promesa":          "Promesa de compraventa",
    "arrendamiento":    "Contrato de arrendamiento",
    "exclusiva":        "Contrato de exclusiva / mediación",
    "carta_intencion":  "Carta de intención",
    "convenio":         "Convenio de colaboración",
    "otro":             "Documento",
}

# El rol no es cosmético: define quién es quién en la constancia y es lo
# primero que revisa un abogado cuando lee el documento.
ROLES = {
    "promitente_vendedor": "Promitente vendedor",
    "promitente_comprador": "Promitente comprador",
    "arrendador":          "Arrendador",
    "arrendatario":        "Arrendatario",
    "fiador":              "Fiador",
    "obligado_solidario":  "Obligado solidario",
    "copropietario":       "Copropietario",
    "conyuge":             "Cónyuge",
    "propietario":         "Propietario",
    "agente_mediador":     "Asesor inmobiliario",
    "testigo":             "Testigo",
    "otro":                "Firmante",
}

# Los tipos donde el agente SÍ puede ser parte. En los demás no debe aparecer,
# y el frontend lo refleja escondiendo el rol.
TIPOS_CON_AGENTE = {"exclusiva", "convenio"}

# ── El texto del consentimiento ───────────────────────────────────────────
# Esto es lo que sostiene todo lo demás. Si alguien impugna la firma, lo
# primero que se lee es qué aceptó exactamente la persona. Se guarda copiado
# literal en cada firmante: si mañana cambia la redacción, lo que se firmó
# ayer conserva el texto de ayer.
#
# Revisar con abogado antes del primer uso real. Está escrito para que ese
# ajuste sea editar esta constante y nada más.
CONSENTIMIENTO = (
    "Manifiesto que leí íntegramente el documento que se me presentó, que "
    "entiendo su contenido y alcance, y que es mi voluntad obligarme en sus "
    "términos. Acepto expresamente manifestar mi consentimiento por medios "
    "electrónicos y reconozco que la firma electrónica que produzco en este "
    "acto tiene, respecto de mi persona, el mismo valor y efectos que mi firma "
    "autógrafa, en términos de los artículos 89 a 114 del Código de Comercio. "
    "Reconozco que quedará registrada la fecha y hora de mi firma, la dirección "
    "IP desde la que firmo, el dispositivo que utilizo, la ubicación aproximada "
    "que autorice compartir y el código de verificación que recibí, y consiento "
    "que esa información se conserve como evidencia del acto. Confirmo que el "
    "número de teléfono o correo donde recibí el código de verificación es mío "
    "y está bajo mi control exclusivo."
)


# ══════════════════════════════════════════════════════════════════════════
# INFRAESTRUCTURA
# ══════════════════════════════════════════════════════════════════════════

def _headers(prefer: Optional[str] = None) -> Dict[str, str]:
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


async def _sb_get(tabla: str, params: dict) -> List[dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(), params=params)
        if r.status_code != 200:
            log.warning("GET %s -> %s %s", tabla, r.status_code, r.text[:180])
            return []
        return r.json()


async def _sb_post(tabla: str, payload, prefer: str = "return=representation") -> List[dict]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(prefer), json=payload)
        if r.status_code not in (200, 201, 204):
            log.warning("POST %s -> %s %s", tabla, r.status_code, r.text[:180])
            raise HTTPException(500, "No se pudo guardar. Intenta de nuevo.")
        try:
            return r.json()
        except Exception:
            return []


async def _sb_patch(tabla: str, params: dict, payload: dict) -> List[dict]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.patch(f"{SUPABASE_URL}/rest/v1/{tabla}",
                          headers=_headers("return=representation"),
                          params=params, json=payload)
        if r.status_code not in (200, 204):
            log.warning("PATCH %s -> %s %s", tabla, r.status_code, r.text[:180])
            raise HTTPException(500, "No se pudo actualizar. Intenta de nuevo.")
        try:
            return r.json()
        except Exception:
            return []


async def _sb_delete(tabla: str, params: dict) -> None:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.delete(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(), params=params)
        if r.status_code not in (200, 204):
            log.warning("DELETE %s -> %s %s", tabla, r.status_code, r.text[:180])
            raise HTTPException(500, "No se pudo borrar. Intenta de nuevo.")


async def get_user_id_from_token(request: Request) -> Optional[str]:
    """Igual que el de main.py. Duplicado a propósito: este router es autónomo."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{SUPABASE_URL}/auth/v1/user",
                            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {auth[7:]}"})
            if r.status_code == 200:
                return r.json().get("id")
    except Exception:
        pass
    return None


async def _uid(request: Request) -> str:
    uid = await get_user_id_from_token(request)
    if not uid:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return uid


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:60]
    return (request.client.host if request.client else "")[:60]


def _ua(request: Request) -> str:
    return (request.headers.get("user-agent", "") or "")[:300]


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


async def evento(user_id: str, tipo: str, detalle: str = "",
                 documento_id: Optional[str] = None,
                 firmante_id: Optional[str] = None,
                 actor: str = "sistema", ip: str = "", ua: str = "",
                 payload: Optional[dict] = None) -> None:
    """Nunca lanza. Una bitácora que falla no debe tumbar la firma que estaba
    registrando; se pierde el renglón, no el acto."""
    try:
        await _sb_post("firma_eventos", {
            "user_id": user_id,
            "documento_id": documento_id,
            "firmante_id": firmante_id,
            "tipo": tipo,
            "detalle": (detalle or "")[:2000] or None,
            "actor": actor,
            "ip": ip or None,
            "user_agent": ua or None,
            "payload": payload,
        }, prefer="return=minimal")
    except Exception as e:
        log.warning("evento falló (%s): %s", tipo, e)


# ── Almacenamiento ────────────────────────────────────────────────────────

def _limpio(nombre: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (nombre or "documento").strip())[:80]
    return base or "documento"


async def _subir_bytes(ruta: str, contenido: bytes, mime: str) -> None:
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(
            f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
            headers={"apikey": SUPABASE_SERVICE_KEY,
                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": mime, "x-upsert": "true"},
            content=contenido)
        if r.status_code not in (200, 201):
            log.warning("upload %s -> %s %s", ruta, r.status_code, r.text[:200])
            raise HTTPException(500, "No se pudo guardar el archivo. Intenta de nuevo.")


async def _bajar_bytes(ruta: str) -> bytes:
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.get(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
                        headers={"apikey": SUPABASE_SERVICE_KEY,
                                 "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"})
        if r.status_code != 200:
            log.warning("download %s -> %s", ruta, r.status_code)
            raise HTTPException(500, "No se pudo leer el archivo guardado.")
        return r.content


async def _liga_firmada(ruta: str, segundos: int) -> str:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{ruta}",
                         headers=_headers(), json={"expiresIn": segundos})
        if r.status_code != 200:
            log.warning("sign %s -> %s %s", ruta, r.status_code, r.text[:200])
            raise HTTPException(500, "No se pudo abrir el archivo.")
        return f"{SUPABASE_URL}/storage/v1" + (r.json().get("signedURL") or "")


async def _borrar_ruta(ruta: str) -> None:
    if not ruta:
        return
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            await c.delete(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
                           headers={"apikey": SUPABASE_SERVICE_KEY,
                                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"})
    except Exception as e:
        log.warning("no se pudo borrar %s: %s", ruta, e)


# ── Folio ─────────────────────────────────────────────────────────────────
# Sin vocales y sin los caracteres que se confunden al dictarlos por teléfono
# (0/O, 1/I/L). Es el número que alguien va a leer en voz alta o teclear en la
# página de verificación.
_ALFABETO_FOLIO = "23456789BCDFGHJKMNPQRSTVWXYZ"


def _folio() -> str:
    cuerpo = "".join(secrets.choice(_ALFABETO_FOLIO) for _ in range(8))
    return f"BRQ-{cuerpo}"


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _fecha_larga(iso: Optional[str]) -> str:
    """Fecha y hora en horario del centro de México, que es donde se firma."""
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        d = d.astimezone(timezone(timedelta(hours=-6)))
        meses = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                 "agosto", "septiembre", "octubre", "noviembre", "diciembre")
        return (f"{d.day} de {meses[d.month - 1]} de {d.year}, "
                f"{d.strftime('%H:%M:%S')} (UTC-6)")
    except Exception:
        return str(iso)


def _tel(v: str) -> str:
    """Normaliza a E.164 mexicano. Un número mal normalizado es un código que
    nunca llega y una firma que nunca ocurre."""
    d = re.sub(r"\D", "", v or "")
    if not d:
        return ""
    if d.startswith("52") and len(d) >= 12:
        return "+" + d[:13]
    if len(d) == 10:
        return "+52" + d
    if d.startswith("521") and len(d) == 13:
        return "+52" + d[3:]
    return "+" + d


def _email_ok(v: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$", (v or "").strip()))


def _mask_tel(v: str) -> str:
    v = v or ""
    return ("•" * max(0, len(v) - 4)) + v[-4:] if len(v) > 4 else "••••"


def _mask_email(v: str) -> str:
    v = v or ""
    if "@" not in v:
        return "••••"
    u, d = v.split("@", 1)
    return (u[0] if u else "") + "•" * max(1, len(u) - 1) + "@" + d


# ══════════════════════════════════════════════════════════════════════════
# ENVÍO DE MENSAJES
# ══════════════════════════════════════════════════════════════════════════

async def _mail(para: str, asunto: str, cuerpo_html: str) -> Tuple[bool, str]:
    """Devuelve (salió, motivo). El motivo importa: decirle al agente
    "no se pudo enviar" y ya lo deja adivinando entre un correo mal escrito,
    un dominio sin verificar y una cuenta en modo prueba. Son problemas muy
    distintos y solo uno lo puede resolver él."""
    if not RESEND_API_KEY:
        return False, "Falta configurar el correo en el servidor (RESEND_API_KEY)."
    if not _email_ok(para):
        return False, "El correo está mal escrito."
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post("https://api.resend.com/emails",
                             headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                                      "Content-Type": "application/json"},
                             json={"from": RESEND_FROM, "to": [para],
                                   "subject": asunto, "html": cuerpo_html})
        if r.status_code in (200, 201, 202):
            return True, ""

        log.warning("resend -> %s %s", r.status_code, r.text[:300])
        try:
            crudo = (r.json() or {}).get("message") or r.text[:200]
        except Exception:
            crudo = r.text[:200]

        # El error más común de todos, traducido a algo accionable. Con el
        # dominio sin verificar, Resend solo deja mandar correos a la propia
        # cuenta y rechaza todo lo demás — que es justo el caso de un
        # comprador o un inquilino.
        bajo = (crudo or "").lower()
        if "testing emails" in bajo or "own email" in bajo:
            motivo = ("El dominio broquer.app no está verificado en Resend, así que solo "
                      "deja mandar correos a tu propia cuenta. Verifícalo en Resend > Domains.")
        elif "domain is not verified" in bajo or "not verified" in bajo:
            motivo = "El dominio del remitente no está verificado en Resend."
        elif r.status_code == 401 or r.status_code == 403:
            motivo = f"Resend rechazó la credencial: {crudo}"
        elif r.status_code == 429:
            motivo = "Resend está limitando el envío por volumen. Intenta en un minuto."
        else:
            motivo = f"Resend respondió {r.status_code}: {crudo}"
        return False, motivo
    except Exception as e:
        log.warning("resend falló: %s", e)
        return False, f"No se pudo contactar al servicio de correo: {e}"


async def _wa_numero(user_id: str) -> Optional[dict]:
    """El primer número de WhatsApp conectado del agente, si tiene."""
    try:
        filas = await _sb_get("wa2_numeros", {
            "user_id": f"eq.{user_id}", "select": "*",
            "order": "created_at.asc", "limit": "1"})
        return filas[0] if filas else None
    except Exception:
        return None


async def _wa_texto(numero: dict, telefono: str, texto: str) -> bool:
    """Texto libre por WhatsApp. Solo llega si hay ventana de 24 horas abierta,
    o sea si esa persona ya le escribió al agente. Para un comprador que nunca
    ha escrito, esto falla con el código 131047 y hay que caer a correo."""
    if not numero or not numero.get("access_token"):
        return False
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"https://graph.facebook.com/v21.0/{numero['phone_number_id']}/messages",
                headers={"Authorization": f"Bearer {numero['access_token']}"},
                json={"messaging_product": "whatsapp", "to": telefono.lstrip("+"),
                      "type": "text", "text": {"body": texto, "preview_url": False}})
        if r.status_code >= 400:
            log.info("wa texto rechazado: %s", r.text[:180])
            return False
        return True
    except Exception as e:
        log.warning("wa texto falló: %s", e)
        return False


async def _wa_plantilla_otp(numero: dict, telefono: str, codigo: str) -> bool:
    """Plantilla categoría AUTHENTICATION. Es la única vía que sí llega a un
    número frío. Requiere que el agente la tenga aprobada en su WABA y que su
    nombre esté en la env var WA_PLANTILLA_OTP."""
    if not WA_PLANTILLA_OTP or not numero or not numero.get("access_token"):
        return False
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"https://graph.facebook.com/v21.0/{numero['phone_number_id']}/messages",
                headers={"Authorization": f"Bearer {numero['access_token']}"},
                json={"messaging_product": "whatsapp", "to": telefono.lstrip("+"),
                      "type": "template",
                      "template": {
                          "name": WA_PLANTILLA_OTP,
                          "language": {"code": "es_MX"},
                          "components": [
                              {"type": "body",
                               "parameters": [{"type": "text", "text": codigo}]},
                              {"type": "button", "sub_type": "url", "index": "0",
                               "parameters": [{"type": "text", "text": codigo}]},
                          ]}})
        if r.status_code >= 400:
            log.info("wa plantilla rechazada: %s", r.text[:180])
            return False
        return True
    except Exception as e:
        log.warning("wa plantilla falló: %s", e)
        return False


def _mail_layout(titulo: str, cuerpo: str, boton_texto: str = "", boton_url: str = "") -> str:
    boton = ""
    if boton_texto and boton_url:
        boton = (
            f'<tr><td style="padding:28px 0 8px;">'
            f'<a href="{html.escape(boton_url)}" '
            f'style="display:inline-block;background:#05203C;color:#ffffff;'
            f'text-decoration:none;padding:14px 28px;border-radius:10px;'
            f'font-weight:700;font-size:15px;">{html.escape(boton_texto)}</a>'
            f'</td></tr>')
    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#F4F6F8;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F4F6F8;padding:32px 16px;">
<tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:14px;padding:36px 32px;font-family:'DM Sans',Helvetica,Arial,sans-serif;color:#0F1B2A;">
<tr><td style="font-size:20px;font-weight:700;letter-spacing:-0.02em;padding-bottom:14px;">{html.escape(titulo)}</td></tr>
<tr><td style="font-size:15px;line-height:1.6;color:#3C4A5A;">{cuerpo}</td></tr>
{boton}
<tr><td style="padding-top:28px;border-top:1px solid #E6EAEF;margin-top:24px;font-size:12px;color:#8A97A6;line-height:1.5;">
Enviado a través de Broquer. Si no esperabas este mensaje, ignóralo y no se realizará ninguna acción.
</td></tr>
</table></td></tr></table></body></html>"""


# ══════════════════════════════════════════════════════════════════════════
# LECTURA Y REGLAS DE TURNO
# ══════════════════════════════════════════════════════════════════════════

async def _doc_del_usuario(documento_id: str, user_id: str) -> dict:
    filas = await _sb_get("firma_documentos",
                          {"id": f"eq.{documento_id}", "user_id": f"eq.{user_id}", "limit": "1"})
    if not filas:
        raise HTTPException(404, "No encontré ese documento.")
    return filas[0]


async def _firmantes(documento_id: str) -> List[dict]:
    return await _sb_get("firma_firmantes", {
        "documento_id": f"eq.{documento_id}", "select": "*",
        "order": "orden.asc.nullsfirst,created_at.asc"})


def _le_toca(firmante: dict, todos: List[dict]) -> bool:
    """Con orden en null todos firman en paralelo. Con orden numérico, a cada
    quien le toca cuando los de números menores ya terminaron. El fiador es el
    caso de siempre: no tiene por qué obligarse si los principales no firmaron."""
    mi_orden = firmante.get("orden")
    if mi_orden is None:
        return True
    for f in todos:
        o = f.get("orden")
        if o is None or o >= mi_orden:
            continue
        if f.get("estado") != "firmado" and f.get("obligatorio", True):
            return False
    return True


def _resumen_estado(doc: dict, firmantes: List[dict]) -> str:
    if doc.get("estado") in ("cancelado", "borrador"):
        return doc["estado"]
    obligatorios = [f for f in firmantes if f.get("obligatorio", True)]
    if any(f.get("estado") == "rechazado" for f in firmantes):
        return "rechazado"
    if obligatorios and all(f.get("estado") == "firmado" for f in obligatorios):
        return "completo"
    if any(f.get("estado") == "firmado" for f in firmantes):
        return "parcial"
    vence = doc.get("vence_at")
    if vence:
        try:
            if datetime.fromisoformat(str(vence).replace("Z", "+00:00")) < datetime.now(timezone.utc):
                return "vencido"
        except Exception:
            pass
    return "enviado"


# ══════════════════════════════════════════════════════════════════════════
# ENDPOINTS DEL AGENTE — DOCUMENTOS
# ══════════════════════════════════════════════════════════════════════════

class DocumentoIn(BaseModel):
    titulo: Optional[str] = None
    tipo: Optional[str] = None
    nivel: Optional[str] = None
    propiedad_id: Optional[str] = None
    mensaje: Optional[str] = None
    exige_ine: Optional[bool] = None
    vence_dias: Optional[int] = None


@router.get("/documentos")
async def listar_documentos(request: Request, estado: str = "", limite: int = 100):
    uid = await _uid(request)
    params: Dict[str, str] = {
        "user_id": f"eq.{uid}", "select": "*",
        "order": "created_at.desc", "limit": str(max(1, min(limite, 300))),
    }
    if estado:
        params["estado"] = f"eq.{estado}"
    docs = await _sb_get("firma_documentos", params)
    if not docs:
        return {"documentos": []}

    ids = ",".join(d["id"] for d in docs)
    firmantes = await _sb_get("firma_firmantes", {
        "documento_id": f"in.({ids})",
        "select": "id,documento_id,nombre,rol,orden,estado,obligatorio,firmado_at"})
    por_doc: Dict[str, List[dict]] = {}
    for f in firmantes:
        por_doc.setdefault(f["documento_id"], []).append(f)

    salida = []
    for d in docs:
        fs = por_doc.get(d["id"], [])
        salida.append({
            **d,
            "firmantes": fs,
            "total_firmantes": len(fs),
            "ya_firmaron": sum(1 for f in fs if f.get("estado") == "firmado"),
        })
    return {"documentos": salida}


@router.post("/documentos")
async def crear_documento(request: Request, body: DocumentoIn):
    uid = await _uid(request)
    titulo = (body.titulo or "").strip()
    if not titulo:
        raise HTTPException(400, "Ponle un título al documento.")
    tipo = (body.tipo or "otro").strip()
    if tipo not in TIPOS:
        tipo = "otro"
    nivel = (body.nivel or "simple").strip()
    if nivel not in ("simple", "reforzado"):
        nivel = "simple"
    dias = body.vence_dias if (body.vence_dias and 1 <= body.vence_dias <= 365) else VIGENCIA_DIAS

    filas = await _sb_post("firma_documentos", {
        "user_id": uid,
        "titulo": titulo[:200],
        "tipo": tipo,
        "nivel": nivel,
        "propiedad_id": body.propiedad_id or None,
        "mensaje": (body.mensaje or "").strip()[:1000] or None,
        "exige_ine": bool(body.exige_ine),
        "folio": _folio(),
        "estado": "borrador",
        "vence_at": (datetime.now(timezone.utc) + timedelta(days=dias)).isoformat(),
    })
    doc = filas[0] if filas else {}
    await evento(uid, "documento_creado", f"Se creó «{titulo}».",
                 documento_id=doc.get("id"), actor="agente", ip=_ip(request), ua=_ua(request))
    return {"documento": doc}


@router.get("/documentos/{documento_id}")
async def ver_documento(request: Request, documento_id: str):
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    firmantes = await _firmantes(documento_id)
    eventos = await _sb_get("firma_eventos", {
        "documento_id": f"eq.{documento_id}", "select": "*",
        "order": "created_at.asc", "limit": "500"})

    # Al agente le interesa saber qué firmante ya tiene expediente PLD: es la
    # diferencia entre "sé quién es" y "confío en que es quien dice".
    con_expediente = {f["expediente_id"] for f in firmantes if f.get("expediente_id")}
    completos: set = set()
    if con_expediente:
        exps = await _sb_get("pld_expedientes", {
            "id": f"in.({','.join(con_expediente)})",
            "select": "id,completitud,estatus"})
        completos = {e["id"] for e in exps if (e.get("completitud") or 0) >= 100}

    for f in firmantes:
        f["identificado"] = bool(f.get("expediente_id") and f["expediente_id"] in completos)
        f["le_toca"] = _le_toca(f, firmantes)

    return {"documento": doc, "firmantes": firmantes, "eventos": eventos,
            "estado_calculado": _resumen_estado(doc, firmantes)}


@router.patch("/documentos/{documento_id}")
async def editar_documento(request: Request, documento_id: str, body: DocumentoIn):
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    if doc.get("estado") not in ("borrador",):
        raise HTTPException(409, "Este documento ya se envió. Cancélalo y crea uno nuevo si necesitas cambiarlo.")

    cambios: Dict[str, Any] = {"updated_at": _ahora()}
    if body.titulo is not None:
        cambios["titulo"] = body.titulo.strip()[:200]
    if body.tipo is not None and body.tipo in TIPOS:
        cambios["tipo"] = body.tipo
    if body.nivel is not None and body.nivel in ("simple", "reforzado"):
        cambios["nivel"] = body.nivel
    if body.mensaje is not None:
        cambios["mensaje"] = body.mensaje.strip()[:1000] or None
    if body.exige_ine is not None:
        cambios["exige_ine"] = bool(body.exige_ine)
    if body.propiedad_id is not None:
        cambios["propiedad_id"] = body.propiedad_id or None
    if body.vence_dias and 1 <= body.vence_dias <= 365:
        cambios["vence_at"] = (datetime.now(timezone.utc) + timedelta(days=body.vence_dias)).isoformat()

    filas = await _sb_patch("firma_documentos", {"id": f"eq.{documento_id}"}, cambios)
    return {"documento": filas[0] if filas else {}}


@router.delete("/documentos/{documento_id}")
async def borrar_documento(request: Request, documento_id: str):
    """Solo borradores. Un documento que ya salió a firma no se borra: se
    cancela. Borrar evidencia de un acto que sí ocurrió es exactamente lo que
    no debe poder hacer nadie, empezando por el dueño de la cuenta."""
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    if doc.get("estado") != "borrador":
        raise HTTPException(409, "Este documento ya salió a firma. Puedes cancelarlo, no borrarlo.")
    for ruta in (doc.get("archivo_ruta"), doc.get("firmado_ruta")):
        await _borrar_ruta(ruta or "")
    await _sb_delete("firma_documentos", {"id": f"eq.{documento_id}", "user_id": f"eq.{uid}"})
    return {"ok": True}


class CancelarIn(BaseModel):
    motivo: Optional[str] = None


@router.post("/documentos/{documento_id}/cancelar")
async def cancelar_documento(request: Request, documento_id: str, body: CancelarIn):
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    if doc.get("estado") == "completo":
        raise HTTPException(409, "Este documento ya se firmó completo. No se puede cancelar.")

    await _sb_patch("firma_documentos", {"id": f"eq.{documento_id}"}, {
        "estado": "cancelado",
        "cancelado_at": _ahora(),
        "motivo_cancelacion": (body.motivo or "").strip()[:500] or None,
        "updated_at": _ahora(),
    })
    # Las ligas dejan de servir en el acto.
    await _sb_patch("firma_firmantes",
                    {"documento_id": f"eq.{documento_id}", "estado": "neq.firmado"},
                    {"token": None})
    await evento(uid, "cancelado", (body.motivo or "El agente canceló el documento.")[:400],
                 documento_id=documento_id, actor="agente", ip=_ip(request), ua=_ua(request))
    return {"ok": True}


# ── El archivo ────────────────────────────────────────────────────────────

@router.post("/documentos/{documento_id}/archivo")
async def subir_archivo(request: Request, documento_id: str, archivo: UploadFile = File(...)):
    """El PDF que se va a firmar. Aquí se le saca el hash y ese hash es el que
    va a aparecer en la constancia: a partir de este momento el archivo queda
    congelado."""
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    if doc.get("estado") not in ("borrador",):
        raise HTTPException(409, "Ya no puedes cambiar el archivo: el documento salió a firma.")

    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(400, "El archivo llegó vacío.")
    if len(contenido) > MAX_PDF_BYTES:
        raise HTTPException(413, "El archivo pesa más de 20 MB. Compártelo más ligero.")

    nombre_final = _limpio(archivo.filename)

    # Si llega un Word se convierte aquí mismo. Se firma el PDF, no el .docx:
    # un Word se abre y se edita sin dejar rastro, y entonces el hash deja de
    # significar nada. Además así el agente no tiene que exportar a mano.
    if contenido[:4] == b"PK\x03\x04" and nombre_final.lower().endswith((".docx", ".dotx")):
        contenido = await _docx_a_pdf_bytes(contenido, doc.get("titulo") or "Documento")
        nombre_final = re.sub(r"\.(docx|dotx)$", ".pdf", nombre_final, flags=re.I)

    if not contenido.startswith(b"%PDF"):
        raise HTTPException(415, "Solo se aceptan archivos PDF o Word (.docx).")

    try:
        import pypdf
        lector = pypdf.PdfReader(io.BytesIO(contenido))
        # Un PDF con contraseña no se puede anexar ni leer: mejor rechazarlo
        # aquí que descubrirlo cuando ya firmaron todos.
        if lector.is_encrypted:
            raise HTTPException(415, "Ese PDF está protegido con contraseña. Quítasela y vuelve a subirlo.")
        paginas = len(lector.pages)
        if paginas < 1:
            raise HTTPException(415, "Ese PDF no tiene páginas legibles.")
    except HTTPException:
        raise
    except Exception as e:
        log.warning("pdf ilegible: %s", e)
        raise HTTPException(415, "No pude leer ese PDF. Ábrelo, vuelve a exportarlo y súbelo de nuevo.")

    await _borrar_ruta(doc.get("archivo_ruta") or "")
    sello = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    ruta = f"{uid}/{documento_id}/original-{sello}-{nombre_final}"
    await _subir_bytes(ruta, contenido, "application/pdf")

    digest = _sha256(contenido)
    filas = await _sb_patch("firma_documentos", {"id": f"eq.{documento_id}"}, {
        "archivo_ruta": ruta,
        "archivo_nombre": nombre_final,
        "archivo_bytes": len(contenido),
        "paginas": paginas,
        "hash_original": digest,
        "updated_at": _ahora(),
    })
    await evento(uid, "archivo_subido",
                 f"Se cargó «{nombre_final}» ({paginas} pág). SHA-256: {digest}",
                 documento_id=documento_id, actor="agente", ip=_ip(request), ua=_ua(request),
                 payload={"sha256": digest, "bytes": len(contenido), "paginas": paginas})
    return {"documento": filas[0] if filas else {}}


# ══════════════════════════════════════════════════════════════════════════
# DESDE EL MÓDULO DE CONTRATOS
# ══════════════════════════════════════════════════════════════════════════
# El agente acaba de llenar el formulario de una promesa o un arrendamiento.
# Los nombres de las partes ya están capturados ahí. Pedirle que descargue el
# Word, lo exporte a PDF, lo vuelva a subir y reteclee a las mismas personas
# sería trabajo que la computadora puede hacer sola.
#
# Se reutiliza generar_contrato.py tal cual, por subproceso, igual que lo
# invoca main.py. Ese archivo tiene el texto legal revisado y no se toca.

async def _docx_a_pdf_bytes(docx: bytes, titulo: str) -> bytes:
    import tempfile
    try:
        from contrato_pdf import docx_a_pdf
    except Exception as e:
        log.error("no se pudo importar contrato_pdf: %s", e)
        raise HTTPException(500, "No se pudo convertir el documento. Súbelo en PDF.")

    ruta = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(docx)
            ruta = f.name
        return await docx_a_pdf(ruta, titulo)
    except HTTPException:
        raise
    except Exception as e:
        log.error("conversión docx->pdf falló: %s", e)
        raise HTTPException(500, "No se pudo convertir ese Word. Ábrelo, expórtalo a PDF y súbelo así.")
    finally:
        if ruta:
            try:
                os.unlink(ruta)
            except Exception:
                pass


class DesdeContratoIn(BaseModel):
    tipo: str                        # promesa | arrendamiento
    datos: Dict[str, Any]
    titulo: Optional[str] = None
    propiedad_id: Optional[str] = None
    exige_ine: Optional[bool] = None


@router.post("/desde-contrato")
async def desde_contrato(request: Request, body: DesdeContratoIn):
    """Genera el contrato, lo convierte a PDF, crea el documento y precarga a
    las partes. Devuelve el id para que el frontend se vaya derecho al módulo
    de firma con todo listo."""
    import json as _json
    import tempfile
    import subprocess

    uid = await _uid(request)
    tipo = (body.tipo or "").strip().lower()
    if tipo not in ("promesa", "arrendamiento"):
        raise HTTPException(400, "Solo se puede mandar a firma una promesa o un arrendamiento.")

    try:
        from contrato_pdf import partes_del_contrato
    except Exception as e:
        log.error("no se pudo importar contrato_pdf: %s", e)
        raise HTTPException(500, "El generador de contratos no está disponible en este momento.")

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(raiz, "generar_contrato.py")
    if not os.path.exists(script):
        raise HTTPException(500, "El generador de contratos no está disponible en este momento.")

    ruta_json = ruta_docx = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            _json.dump(body.datos or {}, f, ensure_ascii=False)
            ruta_json = f.name
        ruta_docx = ruta_json.replace(".json", ".docx")

        r = subprocess.run(["python3", script, tipo, ruta_json, ruta_docx],
                           capture_output=True, text=True, timeout=45)
        if r.returncode != 0 or not os.path.exists(ruta_docx):
            log.error("generar_contrato falló: %s", (r.stderr or "")[:400])
            raise HTTPException(400, "Faltan datos para armar el contrato. Revisa el formulario y vuelve a intentar.")

        etiqueta = (body.titulo or "").strip() or TIPOS.get(tipo, "Documento")
        with open(ruta_docx, "rb") as f:
            docx = f.read()
        pdf = await _docx_a_pdf_bytes(docx, etiqueta)
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "El contrato tardó demasiado en generarse. Intenta de nuevo.")
    finally:
        for p in (ruta_json, ruta_docx):
            if p:
                try:
                    os.unlink(p)
                except Exception:
                    pass

    import pypdf
    try:
        paginas = len(pypdf.PdfReader(io.BytesIO(pdf)).pages)
    except Exception:
        paginas = None

    filas = await _sb_post("firma_documentos", {
        "user_id": uid,
        "titulo": etiqueta[:200],
        "tipo": tipo,
        "nivel": "simple",
        "propiedad_id": body.propiedad_id or None,
        "exige_ine": bool(body.exige_ine),
        "folio": _folio(),
        "estado": "borrador",
        "vence_at": (datetime.now(timezone.utc) + timedelta(days=VIGENCIA_DIAS)).isoformat(),
    })
    if not filas:
        raise HTTPException(500, "No se pudo crear el documento. Intenta de nuevo.")
    doc = filas[0]

    sello = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    ruta = f"{uid}/{doc['id']}/original-{sello}-{tipo}.pdf"
    await _subir_bytes(ruta, pdf, "application/pdf")
    digest = _sha256(pdf)
    await _sb_patch("firma_documentos", {"id": f"eq.{doc['id']}"}, {
        "archivo_ruta": ruta,
        "archivo_nombre": f"{tipo}.pdf",
        "archivo_bytes": len(pdf),
        "paginas": paginas,
        "hash_original": digest,
        "updated_at": _ahora(),
    })

    await evento(uid, "documento_creado",
                 f"Generado desde el módulo de contratos ({TIPOS.get(tipo)}). SHA-256: {digest}",
                 documento_id=doc["id"], actor="agente", ip=_ip(request), ua=_ua(request),
                 payload={"sha256": digest, "paginas": paginas, "origen": "contratos"})

    # Las partes salen del propio contrato. Faltan sus datos de contacto: el
    # formulario de contratos no los pide, así que el agente los completa en
    # la pantalla de firma. Ya no tiene que reteclear los nombres.
    contactos = await _sb_get("contactos", {
        "user_id": f"eq.{uid}", "select": "id,nombre,telefono,email,wa", "limit": "500"})
    por_nombre = {(c.get("nombre") or "").strip().lower(): c for c in contactos}

    creados = []
    for parte in partes_del_contrato(tipo, body.datos or {}):
        c = por_nombre.get(parte["nombre"].strip().lower())
        nuevos = await _sb_post("firma_firmantes", {
            "user_id": uid,
            "documento_id": doc["id"],
            "contacto_id": c.get("id") if c else None,
            "nombre": parte["nombre"][:160],
            "email": (c.get("email") if c else None) or None,
            "telefono": _tel(c.get("wa") or c.get("telefono") or "") if c else None,
            "rol": parte["rol"],
            "obligatorio": True,
            "estado": "pendiente",
        })
        if nuevos:
            creados.append(nuevos[0])

    return {"documento_id": doc["id"], "folio": doc.get("folio"),
            "firmantes": creados, "paginas": paginas}


@router.get("/documentos/{documento_id}/archivo")
async def abrir_archivo(request: Request, documento_id: str, cual: str = "original"):
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    ruta = doc.get("firmado_ruta") if cual == "firmado" else doc.get("archivo_ruta")
    if not ruta:
        raise HTTPException(404, "Todavía no hay archivo para mostrar.")
    url = await _liga_firmada(ruta, FIRMA_SEGUNDOS)
    await evento(uid, "descargado", f"El agente abrió el documento ({cual}).",
                 documento_id=documento_id, actor="agente", ip=_ip(request), ua=_ua(request))
    return {"url": url, "expira_segundos": FIRMA_SEGUNDOS}


# ══════════════════════════════════════════════════════════════════════════
# ENDPOINTS DEL AGENTE — FIRMANTES
# ══════════════════════════════════════════════════════════════════════════

class FirmanteIn(BaseModel):
    nombre: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    rol: Optional[str] = None
    orden: Optional[int] = None
    obligatorio: Optional[bool] = None
    contacto_id: Optional[str] = None


@router.post("/documentos/{documento_id}/firmantes")
async def agregar_firmante(request: Request, documento_id: str, body: FirmanteIn):
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    if doc.get("estado") not in ("borrador",):
        raise HTTPException(409, "Ya no puedes agregar firmantes: el documento salió a firma.")

    nombre   = (body.nombre or "").strip()
    email    = (body.email or "").strip().lower()
    telefono = _tel(body.telefono or "")
    if not nombre:
        raise HTTPException(400, "Falta el nombre del firmante.")
    if not email and not telefono:
        raise HTTPException(400, "Necesito al menos un correo o un WhatsApp para mandarle la liga y el código.")
    if email and not _email_ok(email):
        raise HTTPException(400, "Ese correo no se ve bien. Revísalo.")

    rol = (body.rol or "otro").strip()
    if rol not in ROLES:
        rol = "otro"

    # Si el firmante viene del CRM, se le hereda el expediente PLD que ya
    # tenga. Eso es lo que convierte "un desconocido con un celular" en
    # "una persona con identificación oficial en archivo".
    expediente_id = None
    if body.contacto_id:
        cont = await _sb_get("contactos",
                             {"id": f"eq.{body.contacto_id}", "user_id": f"eq.{uid}",
                              "select": "id", "limit": "1"})
        if not cont:
            raise HTTPException(404, "Ese contacto no es tuyo o ya no existe.")
        exps = await _sb_get("pld_expedientes",
                             {"contacto_id": f"eq.{body.contacto_id}", "user_id": f"eq.{uid}",
                              "select": "id", "limit": "1"})
        if exps:
            expediente_id = exps[0]["id"]

    filas = await _sb_post("firma_firmantes", {
        "user_id": uid,
        "documento_id": documento_id,
        "contacto_id": body.contacto_id or None,
        "expediente_id": expediente_id,
        "nombre": nombre[:160],
        "email": email or None,
        "telefono": telefono or None,
        "rol": rol,
        "orden": body.orden if (body.orden and body.orden > 0) else None,
        "obligatorio": True if body.obligatorio is None else bool(body.obligatorio),
        "estado": "pendiente",
    })
    return {"firmante": filas[0] if filas else {}}


@router.patch("/firmantes/{firmante_id}")
async def editar_firmante(request: Request, firmante_id: str, body: FirmanteIn):
    uid = await _uid(request)
    filas = await _sb_get("firma_firmantes",
                          {"id": f"eq.{firmante_id}", "user_id": f"eq.{uid}", "limit": "1"})
    if not filas:
        raise HTTPException(404, "No encontré ese firmante.")
    f = filas[0]
    if f.get("estado") == "firmado":
        raise HTTPException(409, "Esta persona ya firmó. Sus datos quedan como estaban al firmar.")

    cambios: Dict[str, Any] = {}
    if body.nombre is not None:
        cambios["nombre"] = body.nombre.strip()[:160]
    if body.email is not None:
        e = body.email.strip().lower()
        if e and not _email_ok(e):
            raise HTTPException(400, "Ese correo no se ve bien. Revísalo.")
        cambios["email"] = e or None
    if body.telefono is not None:
        cambios["telefono"] = _tel(body.telefono) or None
    if body.rol is not None and body.rol in ROLES:
        cambios["rol"] = body.rol
    if body.orden is not None:
        cambios["orden"] = body.orden if body.orden > 0 else None
    if body.obligatorio is not None:
        cambios["obligatorio"] = bool(body.obligatorio)
    if not cambios:
        return {"firmante": f}

    out = await _sb_patch("firma_firmantes", {"id": f"eq.{firmante_id}"}, cambios)
    return {"firmante": out[0] if out else {}}


@router.delete("/firmantes/{firmante_id}")
async def quitar_firmante(request: Request, firmante_id: str):
    uid = await _uid(request)
    filas = await _sb_get("firma_firmantes",
                          {"id": f"eq.{firmante_id}", "user_id": f"eq.{uid}", "limit": "1"})
    if not filas:
        raise HTTPException(404, "No encontré ese firmante.")
    if filas[0].get("estado") == "firmado":
        raise HTTPException(409, "Esta persona ya firmó. No se puede quitar del documento.")
    await _sb_delete("firma_firmantes", {"id": f"eq.{firmante_id}", "user_id": f"eq.{uid}"})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# ENVIAR A FIRMA
# ══════════════════════════════════════════════════════════════════════════

async def _liga_de(firmante: dict) -> str:
    return f"{APP_URL}/firmar.html?t={firmante.get('token') or ''}"


async def _invitar(doc: dict, firmante: dict, agente: str) -> Tuple[bool, str, str]:
    """Manda la liga. Devuelve (llegó, por dónde, motivo si no llegó).
    Se intenta WhatsApp primero porque es donde la gente sí lee, y se cae a
    correo sin drama."""
    url = await _liga_de(firmante)
    tipo_label = TIPOS.get(doc.get("tipo") or "otro", "Documento")
    rol_label = ROLES.get(firmante.get("rol") or "otro", "Firmante")
    canales = []
    fallas = []

    if firmante.get("telefono"):
        numero = await _wa_numero(doc["user_id"])
        if not numero:
            fallas.append("no tienes ningún número de WhatsApp conectado")
        else:
            texto = (
                f"Hola {firmante.get('nombre', '')}.\n\n"
                f"{agente} te comparte un documento para firmar: "
                f"{doc.get('titulo')} ({tipo_label}).\n"
                f"Firmas como: {rol_label}.\n\n"
                f"Ábrelo aquí:\n{url}\n\n"
                f"Folio {doc.get('folio')}. No compartas esta liga: es solo tuya."
            )
            if await _wa_texto(numero, firmante["telefono"], texto):
                canales.append("whatsapp")
            else:
                fallas.append("por WhatsApp no salió porque esa persona nunca te ha escrito "
                              "(la ventana de 24 horas está cerrada)")

    if firmante.get("email"):
        cuerpo = (
            f"<p><strong>{html.escape(agente)}</strong> te comparte un documento para firmar.</p>"
            f"<p style='background:#F4F6F8;border-radius:10px;padding:16px;margin:18px 0;'>"
            f"<strong>{html.escape(doc.get('titulo') or '')}</strong><br/>"
            f"{html.escape(tipo_label)}<br/>"
            f"Firmas como: <strong>{html.escape(rol_label)}</strong><br/>"
            f"Folio: {html.escape(doc.get('folio') or '')}</p>"
            f"<p>Al abrir la liga podrás leer el documento completo antes de decidir. "
            f"Te pediremos un código de verificación para confirmar que eres tú.</p>"
            f"<p style='font-size:13px;color:#8A97A6;'>No compartas esta liga: es solo tuya.</p>"
        )
        ok_mail, motivo_mail = await _mail(
            firmante["email"], f"Documento para firmar — {doc.get('titulo')}",
            _mail_layout("Tienes un documento para firmar", cuerpo, "Abrir y revisar", url))
        if ok_mail:
            canales.append("correo")
        else:
            fallas.append(motivo_mail)
    elif not firmante.get("telefono"):
        fallas.append("no tiene correo ni WhatsApp capturado")

    return (bool(canales),
            " y ".join(canales) if canales else "",
            " · ".join(f for f in fallas if f))


async def _nombre_agente(user_id: str) -> str:
    try:
        filas = await _sb_get("perfiles", {"user_id": f"eq.{user_id}",
                                           "select": "nombre,nombre_publico", "limit": "1"})
        if filas:
            return (filas[0].get("nombre_publico") or filas[0].get("nombre") or "Tu asesor").strip()
    except Exception:
        pass
    return "Tu asesor"


@router.post("/documentos/{documento_id}/enviar")
async def enviar_a_firma(request: Request, documento_id: str):
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    if doc.get("estado") not in ("borrador",):
        raise HTTPException(409, "Este documento ya se envió.")
    if not doc.get("archivo_ruta") or not doc.get("hash_original"):
        raise HTTPException(400, "Primero sube el PDF que se va a firmar.")

    firmantes = await _firmantes(documento_id)
    if not firmantes:
        raise HTTPException(400, "Agrega por lo menos un firmante.")
    if not any(f.get("obligatorio", True) for f in firmantes):
        raise HTTPException(400, "Al menos un firmante tiene que ser obligatorio.")

    agente = await _nombre_agente(uid)
    resultados = []
    for f in firmantes:
        token = secrets.token_urlsafe(32)
        await _sb_patch("firma_firmantes", {"id": f"eq.{f['id']}"},
                        {"token": token, "estado": "pendiente"})
        f["token"] = token
        # A quien no le toca todavía se le crea la liga pero no se le avisa:
        # recibir "firma esto" cuando no puede firmar solo genera llamadas.
        if not _le_toca(f, firmantes):
            resultados.append({"firmante": f["nombre"], "enviado": False, "canal": "en espera de turno"})
            continue
        ok, canal, motivo = await _invitar(doc, f, agente)
        resultados.append({"firmante": f["nombre"], "enviado": ok,
                           "canal": canal, "motivo": motivo})
        await evento(uid, "enviado",
                     f"Invitación a {f['nombre']}" +
                     (f" por {canal}." if ok else f" NO se pudo entregar: {motivo}"),
                     documento_id=documento_id, firmante_id=f["id"], actor="agente",
                     ip=_ip(request), ua=_ua(request))

    await _sb_patch("firma_documentos", {"id": f"eq.{documento_id}"},
                    {"estado": "enviado", "updated_at": _ahora()})
    return {"ok": True, "resultados": resultados}


@router.post("/firmantes/{firmante_id}/recordar")
async def recordar(request: Request, firmante_id: str):
    uid = await _uid(request)
    filas = await _sb_get("firma_firmantes",
                          {"id": f"eq.{firmante_id}", "user_id": f"eq.{uid}", "limit": "1"})
    if not filas:
        raise HTTPException(404, "No encontré ese firmante.")
    f = filas[0]
    if f.get("estado") == "firmado":
        raise HTTPException(409, "Esta persona ya firmó.")
    if not f.get("token"):
        raise HTTPException(409, "Este documento todavía no se envía a firma.")

    doc = await _doc_del_usuario(f["documento_id"], uid)
    todos = await _firmantes(f["documento_id"])
    if not _le_toca(f, todos):
        raise HTTPException(409, "Todavía no le toca a esta persona: faltan firmas anteriores.")

    ok, canal, motivo = await _invitar(doc, f, await _nombre_agente(uid))
    await evento(uid, "recordatorio",
                 f"Recordatorio a {f['nombre']}" +
                 (f" por {canal}." if ok else f" NO se pudo entregar: {motivo}"),
                 documento_id=doc["id"], firmante_id=f["id"], actor="agente",
                 ip=_ip(request), ua=_ua(request))
    if not ok:
        raise HTTPException(502, motivo or "No se pudo entregar el recordatorio.")
    return {"ok": True, "canal": canal}


# ══════════════════════════════════════════════════════════════════════════
# ZONA PÚBLICA — aquí no hay sesión. Quien entra es el cliente del agente.
# ══════════════════════════════════════════════════════════════════════════

async def _por_token(token: str) -> Tuple[dict, dict, List[dict]]:
    if not token or len(token) < 20:
        raise HTTPException(404, "Liga no válida.")
    filas = await _sb_get("firma_firmantes", {"token": f"eq.{token}", "select": "*", "limit": "1"})
    if not filas:
        raise HTTPException(404, "Esta liga ya no está disponible. Pídele una nueva a tu asesor.")
    firmante = filas[0]

    docs = await _sb_get("firma_documentos", {"id": f"eq.{firmante['documento_id']}", "limit": "1"})
    if not docs:
        raise HTTPException(404, "Este documento ya no está disponible.")
    doc = docs[0]

    if doc.get("estado") == "cancelado":
        raise HTTPException(410, "Tu asesor canceló este documento. Ponte en contacto con él.")
    vence = doc.get("vence_at")
    if vence and firmante.get("estado") != "firmado":
        try:
            if datetime.fromisoformat(str(vence).replace("Z", "+00:00")) < datetime.now(timezone.utc):
                raise HTTPException(410, "Esta invitación ya venció. Pídele una nueva a tu asesor.")
        except HTTPException:
            raise
        except Exception:
            pass

    todos = await _firmantes(doc["id"])
    return doc, firmante, todos


@router.get("/publico/{token}")
async def publico_leer(request: Request, token: str):
    """Lo que ve el firmante al abrir la liga. Devuelve SOLO lo necesario: no
    ve los datos de contacto de las otras partes, ni las notas internas del
    agente, ni nada del CRM."""
    doc, firmante, todos = await _por_token(token)

    if firmante.get("estado") == "pendiente":
        await _sb_patch("firma_firmantes", {"id": f"eq.{firmante['id']}"}, {"estado": "abierto"})
        await evento(doc["user_id"], "liga_abierta",
                     f"{firmante['nombre']} abrió la liga.",
                     documento_id=doc["id"], firmante_id=firmante["id"],
                     actor="firmante", ip=_ip(request), ua=_ua(request))

    return {
        "documento": {
            "titulo": doc.get("titulo"),
            "tipo": doc.get("tipo"),
            "tipo_label": TIPOS.get(doc.get("tipo") or "otro", "Documento"),
            "folio": doc.get("folio"),
            "mensaje": doc.get("mensaje"),
            "paginas": doc.get("paginas"),
            "hash_original": doc.get("hash_original"),
            "exige_ine": bool(doc.get("exige_ine")),
            "vence_at": doc.get("vence_at"),
            "estado": _resumen_estado(doc, todos),
        },
        "agente": await _nombre_agente(doc["user_id"]),
        "firmante": {
            "nombre": firmante.get("nombre"),
            "rol": firmante.get("rol"),
            "rol_label": ROLES.get(firmante.get("rol") or "otro", "Firmante"),
            "estado": firmante.get("estado"),
            "firmado_at": firmante.get("firmado_at"),
            "tiene_ine": bool(firmante.get("ine_frente_ruta")),
            "canal_tel": _mask_tel(firmante.get("telefono") or "") if firmante.get("telefono") else None,
            "canal_email": _mask_email(firmante.get("email") or "") if firmante.get("email") else None,
        },
        # De las demás partes solo el nombre y si ya firmaron. Nada más.
        "partes": [{"nombre": f.get("nombre"),
                    "rol_label": ROLES.get(f.get("rol") or "otro", "Firmante"),
                    "firmado": f.get("estado") == "firmado",
                    "es_tu": f["id"] == firmante["id"]} for f in todos],
        "le_toca": _le_toca(firmante, todos),
        "consentimiento": CONSENTIMIENTO,
        # Dónde va a quedar su firma. Firmar sin saber en qué parte del
        # documento va a aparecer el trazo es firmar a ciegas.
        "colocacion": await _donde_firma(doc["id"], firmante["id"]),
    }


async def _donde_firma(documento_id: str, firmante_id: str) -> dict:
    """Resume en una frase dónde va a quedar la firma de esta persona."""
    campos = await _sb_get("firma_campos", {
        "documento_id": f"eq.{documento_id}", "firmante_id": f"eq.{firmante_id}",
        "select": "pagina,tipo"})
    if not campos:
        return {"hay": False, "texto": ""}

    firmas_p = sorted({int(c["pagina"]) for c in campos if c.get("tipo") == "firma"})
    rubricas = sorted({int(c["pagina"]) for c in campos if c.get("tipo") == "rubrica"})

    partes = []
    if firmas_p:
        if len(firmas_p) == 1:
            partes.append(f"tu firma en la hoja {firmas_p[0]}")
        else:
            partes.append("tu firma en las hojas " + ", ".join(str(p) for p in firmas_p))
    if rubricas:
        if len(rubricas) == 1:
            partes.append(f"tu rúbrica al margen de la hoja {rubricas[0]}")
        elif rubricas == list(range(rubricas[0], rubricas[-1] + 1)):
            partes.append(f"tu rúbrica al margen de las {len(rubricas)} hojas")
        else:
            partes.append("tu rúbrica al margen de las hojas " +
                          ", ".join(str(p) for p in rubricas))

    return {"hay": True, "texto": "Al firmar se colocará " + " y ".join(partes) + "."}


@router.get("/publico/{token}/archivo")
async def publico_archivo(request: Request, token: str):
    """La liga firmada del PDF. Nunca se expone la ruta cruda del bucket."""
    doc, firmante, _ = await _por_token(token)
    ruta = doc.get("firmado_ruta") if firmante.get("estado") == "firmado" and doc.get("firmado_ruta") \
        else doc.get("archivo_ruta")
    if not ruta:
        raise HTTPException(404, "Todavía no hay documento que mostrar.")
    url = await _liga_firmada(ruta, FIRMA_SEGUNDOS)
    await evento(doc["user_id"], "documento_visto",
                 f"{firmante['nombre']} abrió el documento.",
                 documento_id=doc["id"], firmante_id=firmante["id"],
                 actor="firmante", ip=_ip(request), ua=_ua(request))
    return {"url": url, "expira_segundos": FIRMA_SEGUNDOS}


@router.post("/publico/{token}/ine")
async def publico_ine(request: Request, token: str,
                      cara: str = Form(...), archivo: UploadFile = File(...)):
    """Identificación del firmante. Es el flujo ligero: dos fotos, sin pedirle
    expediente PLD completo a alguien que no es cliente del agente. Si ya tiene
    expediente, el agente ni siquiera prende esta opción."""
    doc, firmante, _ = await _por_token(token)
    if firmante.get("estado") == "firmado":
        raise HTTPException(409, "Ya firmaste este documento.")
    if cara not in ("frente", "reverso"):
        raise HTTPException(400, "Indica si es el frente o el reverso.")

    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(400, "La foto llegó vacía.")
    if len(contenido) > MAX_IMG_BYTES:
        raise HTTPException(413, "Esa foto pesa más de 8 MB. Tómala de nuevo con menos resolución.")
    mime = (archivo.content_type or "").lower()
    if mime not in MIMES_IMG:
        raise HTTPException(415, "Sube una foto (JPG, PNG o WEBP).")

    sello = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    ruta = f"{doc['user_id']}/{doc['id']}/ine-{firmante['id']}-{cara}-{sello}"
    await _subir_bytes(ruta, contenido, mime)
    await _sb_patch("firma_firmantes", {"id": f"eq.{firmante['id']}"},
                    {f"ine_{cara}_ruta": ruta})
    await evento(doc["user_id"], "ine_subida",
                 f"{firmante['nombre']} subió el {cara} de su identificación.",
                 documento_id=doc["id"], firmante_id=firmante["id"],
                 actor="firmante", ip=_ip(request), ua=_ua(request))
    return {"ok": True, "cara": cara}


# ── El código de verificación ─────────────────────────────────────────────

def _hash_otp(token: str, codigo: str) -> str:
    """El código se guarda hasheado y amarrado al token del firmante. Así ni
    con acceso de lectura a la tabla se puede firmar por alguien más, y un
    código filtrado no sirve en otra liga."""
    return hashlib.sha256(f"{token}:{codigo}".encode()).hexdigest()


@router.post("/publico/{token}/codigo")
async def publico_pedir_codigo(request: Request, token: str, canal: str = Form("")):
    doc, firmante, todos = await _por_token(token)
    if firmante.get("estado") == "firmado":
        raise HTTPException(409, "Ya firmaste este documento.")
    if not _le_toca(firmante, todos):
        raise HTTPException(409, "Todavía no es tu turno: faltan firmas antes que la tuya.")

    # Freno anti-spam. Sin esto, una liga filtrada se convierte en una máquina
    # de mandar SMS y correos a costa del agente.
    ultimo = firmante.get("otp_enviado_at")
    if ultimo:
        try:
            if datetime.fromisoformat(str(ultimo).replace("Z", "+00:00")) > \
                    datetime.now(timezone.utc) - timedelta(seconds=45):
                raise HTTPException(429, "Espera unos segundos antes de pedir otro código.")
        except HTTPException:
            raise
        except Exception:
            pass

    codigo = "".join(secrets.choice("0123456789") for _ in range(OTP_DIGITOS))
    expira = datetime.now(timezone.utc) + timedelta(minutes=OTP_MINUTOS)

    prefiere_wa = (canal or "").strip() == "whatsapp" or not firmante.get("email")
    usado = ""

    if firmante.get("telefono") and prefiere_wa:
        numero = await _wa_numero(doc["user_id"])
        if numero:
            if await _wa_plantilla_otp(numero, firmante["telefono"], codigo):
                usado = "whatsapp"
            else:
                texto = (f"Tu código para firmar «{doc.get('titulo')}» es: {codigo}\n\n"
                         f"Vence en {OTP_MINUTOS} minutos. No se lo compartas a nadie, "
                         f"ni siquiera a tu asesor.")
                if await _wa_texto(numero, firmante["telefono"], texto):
                    usado = "whatsapp"

    if not usado and firmante.get("email"):
        cuerpo = (
            f"<p>Tu código para firmar <strong>{html.escape(doc.get('titulo') or '')}</strong> es:</p>"
            f"<p style='font-size:34px;font-weight:700;letter-spacing:10px;"
            f"background:#F4F6F8;border-radius:10px;padding:20px;text-align:center;"
            f"margin:20px 0;color:#0F1B2A;'>{codigo}</p>"
            f"<p>Vence en {OTP_MINUTOS} minutos.</p>"
            f"<p><strong>No le compartas este código a nadie, ni siquiera a tu asesor.</strong> "
            f"Es la prueba de que fuiste tú quien firmó.</p>"
        )
        ok_mail, motivo_mail = await _mail(firmante["email"], f"Tu código de firma: {codigo}",
                                           _mail_layout("Código de verificación", cuerpo))
        if ok_mail:
            usado = "correo"
        else:
            log.warning("otp por correo falló: %s", motivo_mail)

    if not usado:
        await evento(doc["user_id"], "otp_fallido",
                     f"No se pudo entregar el código a {firmante['nombre']}.",
                     documento_id=doc["id"], firmante_id=firmante["id"],
                     actor="sistema", ip=_ip(request), ua=_ua(request))
        raise HTTPException(502, "No pudimos enviarte el código. Avísale a tu asesor para que revise "
                                 "tu correo o tu número.")

    await _sb_patch("firma_firmantes", {"id": f"eq.{firmante['id']}"}, {
        "otp_hash": _hash_otp(token, codigo),
        "otp_expira_at": expira.isoformat(),
        "otp_intentos": 0,
        "otp_canal": "whatsapp" if usado == "whatsapp" else "email",
        "otp_enviado_at": _ahora(),
    })
    await evento(doc["user_id"], "otp_enviado",
                 f"Código enviado a {firmante['nombre']} por {usado}.",
                 documento_id=doc["id"], firmante_id=firmante["id"],
                 actor="sistema", ip=_ip(request), ua=_ua(request))
    return {"ok": True, "canal": usado, "minutos": OTP_MINUTOS,
            "destino": _mask_tel(firmante.get("telefono") or "") if usado == "whatsapp"
                       else _mask_email(firmante.get("email") or "")}


# ── Firmar ────────────────────────────────────────────────────────────────

class FirmarIn(BaseModel):
    codigo: str
    trazo: str                       # data URL PNG del canvas
    acepto: bool
    geo_lat: Optional[float] = None
    geo_lng: Optional[float] = None
    geo_precision: Optional[float] = None


@router.post("/publico/{token}/firmar")
async def publico_firmar(request: Request, token: str, body: FirmarIn):
    doc, firmante, todos = await _por_token(token)

    if firmante.get("estado") == "firmado":
        raise HTTPException(409, "Ya firmaste este documento.")
    if firmante.get("estado") == "rechazado":
        raise HTTPException(409, "Ya rechazaste este documento.")
    if not _le_toca(firmante, todos):
        raise HTTPException(409, "Todavía no es tu turno: faltan firmas antes que la tuya.")
    if not body.acepto:
        raise HTTPException(400, "Necesitas aceptar los términos para poder firmar.")
    if doc.get("exige_ine") and not firmante.get("ine_frente_ruta"):
        raise HTTPException(400, "Sube tu identificación oficial antes de firmar.")

    # ── Código ──
    if not firmante.get("otp_hash") or not firmante.get("otp_expira_at"):
        raise HTTPException(400, "Pide tu código de verificación antes de firmar.")
    try:
        if datetime.fromisoformat(str(firmante["otp_expira_at"]).replace("Z", "+00:00")) \
                < datetime.now(timezone.utc):
            raise HTTPException(400, "Tu código venció. Pide uno nuevo.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Pide tu código de verificación de nuevo.")

    if (firmante.get("otp_intentos") or 0) >= OTP_INTENTOS:
        raise HTTPException(429, "Demasiados intentos fallidos. Pide un código nuevo.")

    codigo = re.sub(r"\D", "", body.codigo or "")
    if not secrets.compare_digest(_hash_otp(token, codigo), firmante["otp_hash"]):
        await _sb_patch("firma_firmantes", {"id": f"eq.{firmante['id']}"},
                        {"otp_intentos": (firmante.get("otp_intentos") or 0) + 1})
        await evento(doc["user_id"], "otp_fallido",
                     f"Código incorrecto de {firmante['nombre']}.",
                     documento_id=doc["id"], firmante_id=firmante["id"],
                     actor="firmante", ip=_ip(request), ua=_ua(request))
        raise HTTPException(400, "El código no coincide. Revísalo y vuelve a intentar.")

    # ── Trazo ──
    trazo = body.trazo or ""
    if not trazo.startswith("data:image/png;base64,"):
        raise HTTPException(400, "No recibí tu firma. Vuelve a trazarla.")
    import base64
    try:
        png = base64.b64decode(trazo.split(",", 1)[1])
    except Exception:
        raise HTTPException(400, "No pude leer tu firma. Vuelve a trazarla.")
    if len(png) > MAX_TRAZO_BYTES:
        raise HTTPException(413, "El trazo llegó demasiado pesado. Vuelve a firmar.")
    if len(png) < 400:
        raise HTTPException(400, "El trazo quedó vacío. Firma dentro del recuadro.")

    sello = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    ruta_trazo = f"{doc['user_id']}/{doc['id']}/trazo-{firmante['id']}-{sello}.png"
    await _subir_bytes(ruta_trazo, png, "image/png")

    ahora = _ahora()
    await _sb_patch("firma_firmantes", {"id": f"eq.{firmante['id']}"}, {
        "estado": "firmado",
        "firmado_at": ahora,
        "verificado_at": ahora,
        "trazo_ruta": ruta_trazo,
        "ip": _ip(request),
        "user_agent": _ua(request),
        "geo_lat": body.geo_lat,
        "geo_lng": body.geo_lng,
        "geo_precision": body.geo_precision,
        "consentimiento_at": ahora,
        "consentimiento_texto": CONSENTIMIENTO,
        # El código ya cumplió: se invalida en el acto. Guardarlo un minuto más
        # de lo necesario solo agrega superficie de ataque.
        "otp_hash": None,
        "otp_expira_at": None,
    })
    await evento(doc["user_id"], "consentimiento",
                 f"{firmante['nombre']} aceptó el texto de consentimiento.",
                 documento_id=doc["id"], firmante_id=firmante["id"],
                 actor="firmante", ip=_ip(request), ua=_ua(request),
                 payload={"canal_codigo": firmante.get("otp_canal")})
    await evento(doc["user_id"], "firmado",
                 f"{firmante['nombre']} ({ROLES.get(firmante.get('rol') or 'otro', 'Firmante')}) firmó.",
                 documento_id=doc["id"], firmante_id=firmante["id"],
                 actor="firmante", ip=_ip(request), ua=_ua(request),
                 payload={"geo": [body.geo_lat, body.geo_lng] if body.geo_lat else None})

    # ── ¿Se cerró el documento? ──
    todos = await _firmantes(doc["id"])
    obligatorios = [f for f in todos if f.get("obligatorio", True)]
    completo = bool(obligatorios) and all(f.get("estado") == "firmado" for f in obligatorios)

    if completo:
        await _sb_patch("firma_documentos", {"id": f"eq.{doc['id']}"},
                        {"estado": "completo", "completado_at": ahora, "updated_at": ahora})
        try:
            await _sellar(doc["id"])
        except Exception as e:
            # Que falle el armado del PDF no invalida las firmas: ya están en
            # la base con toda su evidencia. Se puede reintentar.
            log.error("sellado falló para %s: %s", doc["id"], e)
            await evento(doc["user_id"], "sellado",
                         f"El armado del documento final falló: {e}. Las firmas están guardadas; "
                         f"se puede reintentar desde el módulo.",
                         documento_id=doc["id"], actor="sistema")
        await _avisar_cierre(doc["id"])
    else:
        await _sb_patch("firma_documentos", {"id": f"eq.{doc['id']}"},
                        {"estado": "parcial", "updated_at": ahora})
        await _avisar_siguiente_turno(doc["id"])

    return {"ok": True, "completo": completo}


class RechazarIn(BaseModel):
    motivo: Optional[str] = None


@router.post("/publico/{token}/rechazar")
async def publico_rechazar(request: Request, token: str, body: RechazarIn):
    """Poder decir que no es parte de poder decir que sí. Un flujo donde la
    única salida es firmar no produce consentimiento, produce presión."""
    doc, firmante, _ = await _por_token(token)
    if firmante.get("estado") == "firmado":
        raise HTTPException(409, "Ya firmaste este documento.")

    await _sb_patch("firma_firmantes", {"id": f"eq.{firmante['id']}"}, {
        "estado": "rechazado",
        "rechazado_at": _ahora(),
        "motivo_rechazo": (body.motivo or "").strip()[:800] or None,
        "ip": _ip(request),
        "user_agent": _ua(request),
        "otp_hash": None,
        "otp_expira_at": None,
    })
    await evento(doc["user_id"], "rechazado",
                 f"{firmante['nombre']} no firmó." +
                 (f" Motivo: {body.motivo.strip()[:400]}" if body.motivo else ""),
                 documento_id=doc["id"], firmante_id=firmante["id"],
                 actor="firmante", ip=_ip(request), ua=_ua(request))

    agente_mail = await _correo_agente(doc["user_id"])
    if agente_mail:
        cuerpo = (f"<p><strong>{html.escape(firmante['nombre'])}</strong> no firmó "
                  f"«{html.escape(doc.get('titulo') or '')}».</p>"
                  + (f"<p>Motivo: {html.escape(body.motivo.strip()[:400])}</p>" if body.motivo else "")
                  + "<p>El documento queda detenido hasta que lo resuelvas.</p>")
        await _mail(agente_mail, f"Firma rechazada — {doc.get('titulo')}",
                    _mail_layout("Un firmante rechazó el documento", cuerpo))
    return {"ok": True}


async def _correo_agente(user_id: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                            headers={"apikey": SUPABASE_SERVICE_KEY,
                                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"})
            if r.status_code == 200:
                return (r.json() or {}).get("email") or ""
    except Exception:
        pass
    return ""


async def _avisar_siguiente_turno(documento_id: str) -> None:
    """Cuando la firma es en cascada, al terminar uno hay que avisarle al que
    sigue. Sin esto la cadena se para y nadie sabe por qué."""
    docs = await _sb_get("firma_documentos", {"id": f"eq.{documento_id}", "limit": "1"})
    if not docs:
        return
    doc = docs[0]
    todos = await _firmantes(documento_id)
    agente = await _nombre_agente(doc["user_id"])
    for f in todos:
        if f.get("estado") in ("firmado", "rechazado"):
            continue
        if f.get("orden") is None:
            continue
        if not _le_toca(f, todos):
            continue
        if f.get("otp_enviado_at") or f.get("estado") == "abierto":
            continue
        ok, canal, motivo = await _invitar(doc, f, agente)
        await evento(doc["user_id"], "enviado",
                     f"Le tocó su turno a {f['nombre']}" +
                     (f"; avisado por {canal}." if ok else f"; NO se le pudo avisar: {motivo}"),
                     documento_id=documento_id, firmante_id=f["id"], actor="sistema")


async def _avisar_cierre(documento_id: str) -> None:
    docs = await _sb_get("firma_documentos", {"id": f"eq.{documento_id}", "limit": "1"})
    if not docs:
        return
    doc = docs[0]
    firmantes = await _firmantes(documento_id)
    verificar = f"{APP_URL}/verificar-firma.html?f={doc.get('folio')}"

    for f in firmantes:
        if not f.get("email"):
            continue
        cuerpo = (
            f"<p>El documento <strong>{html.escape(doc.get('titulo') or '')}</strong> "
            f"quedó firmado por todas las partes.</p>"
            f"<p>Folio: <strong>{html.escape(doc.get('folio') or '')}</strong></p>"
            f"<p>Puedes descargar tu copia con la constancia de firma desde la misma liga "
            f"que usaste para firmar. Consérvala.</p>"
        )
        await _mail(f["email"], f"Documento firmado — {doc.get('titulo')}",
                    _mail_layout("Listo, quedó firmado", cuerpo, "Verificar documento", verificar))

    agente_mail = await _correo_agente(doc["user_id"])
    if agente_mail:
        nombres = ", ".join(f.get("nombre", "") for f in firmantes if f.get("estado") == "firmado")
        cuerpo = (f"<p><strong>{html.escape(doc.get('titulo') or '')}</strong> "
                  f"quedó firmado por todas las partes.</p>"
                  f"<p>Firmaron: {html.escape(nombres)}</p>"
                  f"<p>Folio: <strong>{html.escape(doc.get('folio') or '')}</strong></p>")
        await _mail(agente_mail, f"Documento completo — {doc.get('titulo')}",
                    _mail_layout("Se completó la firma", cuerpo, "Ver documento",
                                 f"{APP_URL}/firmas.html?d={documento_id}"))


# ══════════════════════════════════════════════════════════════════════════
# LA CONSTANCIA
# ══════════════════════════════════════════════════════════════════════════
# La hoja que hace que esto valga algo. Se genera con Playwright igual que el
# resto de los PDFs de la plataforma (ISR, AVM, fichas) y se anexa al final del
# original con pypdf. El original no se toca.
#
# Deliberadamente NO dice "identifiqué plenamente a estas personas". Dice qué
# pasó: qué archivo se presentó, quién lo abrió, desde dónde, con qué código y
# qué texto aceptó. Afirmar identidad plena sería atribuirle al agente una fe
# pública que no tiene, y exponerlo si mañana las partes se pelean.
# ══════════════════════════════════════════════════════════════════════════

def _fila_dato(etiqueta: str, valor: str) -> str:
    return (f'<tr><td class="k">{html.escape(etiqueta)}</td>'
            f'<td class="v">{html.escape(valor or "—")}</td></tr>')


def _constancia_html(doc: dict, firmantes: List[dict], eventos: List[dict],
                     trazos: Dict[str, str], agente: str,
                     campos: Optional[List[dict]] = None) -> str:
    tipo_label = TIPOS.get(doc.get("tipo") or "otro", "Documento")
    verificar = f"{APP_URL}/verificar-firma.html?f={doc.get('folio')}"

    bloques = []
    for i, f in enumerate(firmantes, 1):
        if f.get("estado") != "firmado":
            continue
        geo = "No compartida"
        if f.get("geo_lat") is not None and f.get("geo_lng") is not None:
            prec = f.get("geo_precision")
            geo = f'{f["geo_lat"]:.5f}, {f["geo_lng"]:.5f}'
            if prec:
                geo += f' (±{int(prec)} m)'
        canal = {"whatsapp": "WhatsApp", "email": "Correo electrónico"}.get(f.get("otp_canal") or "", "—")
        destino = _mask_tel(f.get("telefono") or "") if f.get("otp_canal") == "whatsapp" \
            else _mask_email(f.get("email") or "")
        img = trazos.get(f["id"], "")
        trazo_html = (f'<img class="trazo" src="{img}" alt="Firma"/>' if img
                      else '<div class="trazo trazo--vacio">Trazo no disponible</div>')

        bloques.append(f"""
      <section class="firmante">
        <div class="firmante__hd">
          <span class="num">{i}</span>
          <div>
            <div class="nom">{html.escape(f.get('nombre') or '')}</div>
            <div class="rol">{html.escape(ROLES.get(f.get('rol') or 'otro', 'Firmante'))}</div>
          </div>
        </div>
        <div class="firmante__body">
          <div class="trazo-caja">
            {trazo_html}
            <div class="trazo-pie">Trazo capturado en el dispositivo del firmante</div>
          </div>
          <table class="datos">
            {_fila_dato("Firmado el", _fecha_larga(f.get("firmado_at")))}
            {_fila_dato("Código enviado por", f"{canal} a {destino}")}
            {_fila_dato("Código verificado el", _fecha_larga(f.get("verificado_at")))}
            {_fila_dato("Dirección IP", f.get("ip") or "—")}
            {_fila_dato("Ubicación aproximada", geo)}
            {_fila_dato("Identificación en archivo", "Sí" if f.get("ine_frente_ruta") else "No se solicitó")}
            {_fila_dato("Dispositivo", (f.get("user_agent") or "—")[:150])}
          </table>
        </div>
      </section>""")

    filas_ev = []
    for e in eventos:
        quien = {"agente": "Asesor", "firmante": "Firmante", "sistema": "Sistema"}.get(e.get("actor") or "", "—")
        filas_ev.append(
            f'<tr><td class="ts">{html.escape(_fecha_larga(e.get("created_at")))}</td>'
            f'<td class="ac">{html.escape(quien)}</td>'
            f'<td>{html.escape((e.get("detalle") or e.get("tipo") or "")[:220])}</td>'
            f'<td class="ip">{html.escape(e.get("ip") or "—")}</td></tr>')

    consent = firmantes[0].get("consentimiento_texto") if firmantes else CONSENTIMIENTO

    # Dónde quedó cada firma dentro del documento. Esto es lo que sostiene el
    # argumento: no se dice "el archivo es idéntico", se dice "esto se leyó,
    # esto se le agregó, en esta página y en esta posición".
    colocacion = ""
    if campos:
        nombres = {f["id"]: f.get("nombre") or "" for f in firmantes}
        ETIQUETA = {"firma": "Firma", "rubrica": "Rúbrica al margen",
                    "nombre": "Nombre impreso", "fecha": "Fecha"}
        filas_c = []
        # Se agrupan las rúbricas: decir "hojas 1 a 9" es legible; listar
        # nueve renglones idénticos no lo es.
        agrupado: Dict[Any, List[int]] = {}
        for c in campos:
            clave = (c.get("firmante_id"), c.get("tipo") or "firma")
            agrupado.setdefault(clave, []).append(int(c.get("pagina") or 1))
        for (fid, tipo), paginas in agrupado.items():
            paginas = sorted(set(paginas))
            if len(paginas) == 1:
                donde = f"Hoja {paginas[0]}"
            elif paginas == list(range(paginas[0], paginas[-1] + 1)):
                donde = f"Hojas {paginas[0]} a {paginas[-1]}"
            else:
                donde = "Hojas " + ", ".join(str(p) for p in paginas)
            filas_c.append(
                f'<tr><td class="k">{html.escape(nombres.get(fid, "—"))}</td>'
                f'<td class="v">{html.escape(ETIQUETA.get(tipo, "Firma"))} · {donde}</td></tr>')
        if filas_c:
            colocacion = f"""
  <h2>Dónde quedó cada firma en el documento</h2>
  <table class="resumen">{''.join(filas_c)}</table>
  <div class="nota">
    Las firmas que anteceden se colocaron sobre el documento como una capa
    superpuesta, en las posiciones que las partes tenían marcadas al momento
    de firmar. <strong>El texto del documento no fue reescrito ni modificado.</strong>
    El archivo original, sin las firmas superpuestas, se conserva íntegro y su
    huella SHA-256 es la asentada al principio de esta constancia; puede
    cotejarse por separado en la página de verificación.
  </div>"""

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;700&display=swap" rel="stylesheet"/>
<style>
  @page {{ size: A4; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "DM Sans", Helvetica, Arial, sans-serif;
         color: #0F1B2A; font-size: 9.5pt; line-height: 1.5; margin: 0; }}
  .hd {{ border-bottom: 2px solid #05203C; padding-bottom: 10px; margin-bottom: 16px;
         display: flex; justify-content: space-between; align-items: flex-end; }}
  .hd h1 {{ font-size: 16pt; margin: 0; letter-spacing: -0.02em; }}
  .hd .folio {{ font-size: 13pt; font-weight: 700; color: #05203C; }}
  .hd .sub {{ font-size: 8.5pt; color: #5A6875; margin-top: 3px; }}
  h2 {{ font-size: 10pt; text-transform: none; margin: 20px 0 8px;
        padding-bottom: 5px; border-bottom: 1px solid #D9E0E6; }}
  table {{ width: 100%; border-collapse: collapse; }}
  .resumen td {{ padding: 5px 0; vertical-align: top; border-bottom: 1px solid #EEF1F4; }}
  .resumen .k, .datos .k {{ width: 38%; color: #5A6875; }}
  .resumen .v, .datos .v {{ font-weight: 600; }}
  /* Sin monoespaciada: el sistema la tiene prohibida. Se separa con
     letter-spacing para que el hash se pueda cotejar carácter por carácter. */
  .hash {{ font-size: 7.5pt; letter-spacing: 0.06em;
           word-break: break-all; line-height: 1.5; }}
  .firmante {{ border: 1px solid #D9E0E6; border-radius: 6px; padding: 12px 14px;
               margin-bottom: 12px; page-break-inside: avoid; }}
  .firmante__hd {{ display: flex; gap: 10px; align-items: center;
                   border-bottom: 1px solid #EEF1F4; padding-bottom: 8px; margin-bottom: 10px; }}
  .num {{ width: 22px; height: 22px; border-radius: 50%; background: #05203C; color: #fff;
          font-size: 9pt; font-weight: 700; display: flex; align-items: center;
          justify-content: center; flex: none; }}
  .nom {{ font-size: 11pt; font-weight: 700; }}
  .rol {{ font-size: 8.5pt; color: #5A6875; }}
  .firmante__body {{ display: flex; gap: 14px; align-items: flex-start; }}
  .trazo-caja {{ width: 190px; flex: none; }}
  .trazo {{ width: 100%; height: 68px; object-fit: contain;
            border: 1px solid #D9E0E6; border-radius: 4px; background: #fff; }}
  .trazo--vacio {{ display: flex; align-items: center; justify-content: center;
                   font-size: 8pt; color: #8A97A6; }}
  .trazo-pie {{ font-size: 7pt; color: #8A97A6; text-align: center; margin-top: 4px; }}
  .datos {{ flex: 1; font-size: 8.5pt; }}
  .datos td {{ padding: 3px 0; border-bottom: 1px solid #F4F6F8; vertical-align: top; }}
  .bitacora {{ font-size: 7.5pt; }}
  .bitacora th {{ text-align: left; color: #5A6875; font-weight: 600;
                  border-bottom: 1px solid #D9E0E6; padding: 4px 6px 4px 0; }}
  .bitacora td {{ padding: 3px 6px 3px 0; border-bottom: 1px solid #F4F6F8; vertical-align: top; }}
  .bitacora .ts {{ width: 27%; white-space: nowrap; }}
  .bitacora .ac {{ width: 12%; }}
  .bitacora .ip {{ width: 15%; }}
  .nota {{ background: #F4F6F8; border-radius: 6px; padding: 11px 13px;
           font-size: 8pt; line-height: 1.55; color: #3C4A5A; margin-top: 8px; }}
  .pie {{ margin-top: 18px; padding-top: 10px; border-top: 1px solid #D9E0E6;
          font-size: 7.5pt; color: #8A97A6; text-align: center; line-height: 1.6; }}
</style></head><body>

  <div class="hd">
    <div>
      <h1>Constancia de firma electrónica</h1>
      <div class="sub">Generada por Broquer · {html.escape(_fecha_larga(doc.get('completado_at') or _ahora()))}</div>
    </div>
    <div style="text-align:right;">
      <div class="folio">{html.escape(doc.get('folio') or '')}</div>
      <div class="sub">Folio de verificación</div>
    </div>
  </div>

  <h2>El documento</h2>
  <table class="resumen">
    {_fila_dato("Título", doc.get("titulo") or "")}
    {_fila_dato("Naturaleza", tipo_label)}
    {_fila_dato("Archivo presentado", doc.get("archivo_nombre") or "")}
    {_fila_dato("Páginas del documento", str(doc.get("paginas") or "—"))}
    {_fila_dato("Puesto a firma por", agente)}
    {_fila_dato("Firmas recabadas", str(sum(1 for f in firmantes if f.get('estado') == 'firmado')))}
    {_fila_dato("Completado el", _fecha_larga(doc.get("completado_at")))}
    <tr><td class="k">Huella digital del documento (SHA-256)</td>
        <td class="v hash">{html.escape(doc.get('hash_original') or '')}</td></tr>
  </table>
  <div class="nota">
    Esta constancia se anexa al documento original sin modificarlo. Las páginas que
    anteceden son idénticas, byte por byte, al archivo que se presentó a las partes:
    cualquier persona puede recalcular la huella SHA-256 de ese archivo y compararla
    con la asentada arriba en <strong>{html.escape(verificar)}</strong>. Si ambas
    coinciden, el documento no fue alterado después de firmarse.
  </div>

  <h2>Quién firmó y cómo</h2>
  {''.join(bloques) if bloques else '<p>Sin firmas registradas.</p>'}

  {colocacion}

  <h2>Lo que aceptó cada firmante</h2>
  <div class="nota">{html.escape(consent or CONSENTIMIENTO)}</div>

  <h2>Bitácora del proceso</h2>
  <table class="bitacora">
    <thead><tr><th class="ts">Fecha y hora</th><th class="ac">Quién</th>
    <th>Qué ocurrió</th><th class="ip">IP</th></tr></thead>
    <tbody>{''.join(filas_ev)}</tbody>
  </table>

  <div class="nota">
    <strong>Alcance de esta constancia.</strong> Este documento hace constar el proceso
    de firma tal como quedó registrado: los datos que anteceden describen qué archivo se
    presentó, en qué momento cada firmante lo abrió, desde qué dirección IP y dispositivo,
    a qué medio de contacto se envió su código de verificación de un solo uso y en qué
    momento lo introdujo correctamente. No constituye una certificación de identidad ni
    una fe pública sobre las personas firmantes, ni sustituye la intervención de fedatario
    público donde la ley la exija. La firma electrónica aquí recabada se produce al amparo
    de los artículos 89 a 114 del Código de Comercio.
  </div>

  <div class="pie">
    Constancia emitida automáticamente por Broquer · broquer.app<br/>
    Verificable en {html.escape(verificar)} con el folio {html.escape(doc.get('folio') or '')}
  </div>

</body></html>"""


def _capa_html(ancho_pt: float, alto_pt: float, marcas: List[dict]) -> str:
    """La hoja transparente que se pone ENCIMA del contrato.

    Sin fondo y sin margen: lo único que lleva son las firmas en su lugar.
    Playwright la imprime sin pintar blanco, así que el texto del contrato
    sigue viéndose completo debajo. Probado: el original no se tapa."""
    piezas = []
    for m in marcas:
        estilo = (f"left:{m['x'] * 100:.4f}%;top:{m['y'] * 100:.4f}%;"
                  f"width:{m['ancho'] * 100:.4f}%;height:{m['alto'] * 100:.4f}%")
        if m["tipo"] == "rubrica":
            piezas.append(
                f'<div class="m" style="{estilo}">'
                f'<img class="t" src="{m["trazo"]}" alt=""/>'
                f'</div>')
        elif m["tipo"] == "nombre":
            piezas.append(f'<div class="m txt" style="{estilo}">'
                          f'{html.escape(m.get("texto") or "")}</div>')
        elif m["tipo"] == "fecha":
            piezas.append(f'<div class="m txt" style="{estilo}">'
                          f'{html.escape(m.get("texto") or "")}</div>')
        else:
            piezas.append(
                f'<div class="m firma" style="{estilo}">'
                f'<img class="t" src="{m["trazo"]}" alt=""/>'
                f'<div class="pie">{html.escape(m.get("texto") or "")}</div>'
                f'</div>')

    ancho_in = ancho_pt / 72.0
    alto_in = alto_pt / 72.0
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><style>
  @page {{ size: {ancho_in:.4f}in {alto_in:.4f}in; margin: 0; }}
  html, body {{
    margin: 0; padding: 0; background: transparent;
    width: {ancho_in:.4f}in; height: {alto_in:.4f}in; position: relative;
  }}
  .m {{ position: absolute; display: flex; flex-direction: column;
        align-items: center; justify-content: flex-end; overflow: hidden; }}
  .t {{ width: 100%; height: 100%; object-fit: contain; object-position: bottom center; }}
  .firma .t {{ height: 74%; }}
  .pie {{ font-family: Helvetica, Arial, sans-serif; font-size: 6pt;
          color: #333; width: 100%; text-align: center;
          border-top: 0.6pt solid #333; padding-top: 1.5pt;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .txt {{ font-family: Helvetica, Arial, sans-serif; font-size: 8pt;
          color: #111; justify-content: center; }}
</style></head><body>{''.join(piezas)}</body></html>"""


async def _estampar(pdf: bytes, doc: dict, firmantes: List[dict],
                    trazos: Dict[str, str]) -> Tuple[bytes, List[dict]]:
    """Pone las firmas donde el agente las colocó. Devuelve el PDF y el
    detalle de dónde quedó cada una, para que la constancia lo asiente.

    Si no hay campos colocados, devuelve el PDF tal cual: la colocación es
    opcional. Muchos agentes van a subir su contrato y darle enviar sin
    ponerse a arrastrar recuadros, y eso tiene que seguir funcionando."""
    import pypdf
    from playwright.async_api import async_playwright

    campos = await _sb_get("firma_campos", {
        "documento_id": f"eq.{doc['id']}", "select": "*", "order": "pagina.asc"})
    if not campos:
        return pdf, []

    por_id = {f["id"]: f for f in firmantes}
    lector = pypdf.PdfReader(io.BytesIO(pdf))

    # Se agrupan por hoja: una sola capa por página, no una por firma.
    por_pagina: Dict[int, List[dict]] = {}
    asentado: List[dict] = []
    for c in campos:
        f = por_id.get(c.get("firmante_id"))
        if not f or f.get("estado") != "firmado":
            continue
        trazo = trazos.get(f["id"])
        if not trazo:
            continue
        pagina = int(c.get("pagina") or 1)
        if pagina < 1 or pagina > len(lector.pages):
            continue

        texto = ""
        if c.get("tipo") == "firma":
            texto = f.get("nombre") or ""
        elif c.get("tipo") == "nombre":
            texto = f.get("nombre") or ""
        elif c.get("tipo") == "fecha":
            texto = _fecha_larga(f.get("firmado_at")).split(",")[0]

        por_pagina.setdefault(pagina, []).append({
            "tipo": c.get("tipo") or "firma",
            "x": float(c.get("x") or 0), "y": float(c.get("y") or 0),
            "ancho": float(c.get("ancho") or 0.2), "alto": float(c.get("alto") or 0.06),
            "trazo": trazo, "texto": texto,
        })
        asentado.append({
            "firmante": f.get("nombre"), "pagina": pagina,
            "tipo": c.get("tipo") or "firma",
        })

    if not por_pagina:
        return pdf, []

    salida = pypdf.PdfWriter()
    async with async_playwright() as pw:
        navegador = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        pagina_web = await navegador.new_page()
        try:
            for i, pag in enumerate(lector.pages, 1):
                marcas = por_pagina.get(i)
                if marcas:
                    caja = pag.mediabox
                    ancho_pt = float(caja.width)
                    alto_pt = float(caja.height)
                    await pagina_web.set_content(
                        _capa_html(ancho_pt, alto_pt, marcas), wait_until="domcontentloaded")
                    await pagina_web.wait_for_timeout(120)
                    capa = await pagina_web.pdf(
                        width=f"{ancho_pt / 72.0:.4f}in",
                        height=f"{alto_pt / 72.0:.4f}in",
                        print_background=False,
                        margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
                    try:
                        pag.merge_page(pypdf.PdfReader(io.BytesIO(capa)).pages[0])
                    except Exception as e:
                        # Que falle una hoja no debe tirar el documento entero:
                        # esa hoja queda sin la firma encima, pero la firma
                        # sigue asentada en la constancia.
                        log.warning("no se pudo estampar la hoja %s: %s", i, e)
                salida.add_page(pag)
        finally:
            await navegador.close()

    buf = io.BytesIO()
    salida.write(buf)
    return buf.getvalue(), asentado


async def _sellar(documento_id: str) -> None:
    """Arma el entregable: original intacto + constancia anexada al final."""
    import base64
    import pypdf
    from playwright.async_api import async_playwright

    docs = await _sb_get("firma_documentos", {"id": f"eq.{documento_id}", "limit": "1"})
    if not docs:
        raise RuntimeError("documento no encontrado")
    doc = docs[0]
    if not doc.get("archivo_ruta"):
        raise RuntimeError("el documento no tiene archivo original")

    firmantes = await _firmantes(documento_id)
    eventos = await _sb_get("firma_eventos", {
        "documento_id": f"eq.{documento_id}", "select": "*",
        "order": "created_at.asc", "limit": "400"})

    # Los trazos se incrustan en base64: si fueran ligas, la constancia dejaría
    # de verse el día que caduquen y el PDF se volvería inútil.
    trazos: Dict[str, str] = {}
    for f in firmantes:
        if f.get("trazo_ruta"):
            try:
                png = await _bajar_bytes(f["trazo_ruta"])
                trazos[f["id"]] = "data:image/png;base64," + base64.b64encode(png).decode()
            except Exception as e:
                log.warning("no se pudo leer el trazo de %s: %s", f.get("nombre"), e)

    agente = await _nombre_agente(doc["user_id"])

    # Se consulta antes de armar la constancia para poder asentar en ella
    # dónde quedó cada firma dentro del documento.
    campos = await _sb_get("firma_campos", {
        "documento_id": f"eq.{documento_id}", "select": "*", "order": "pagina.asc"})
    html_constancia = _constancia_html(doc, firmantes, eventos, trazos, agente, campos)

    # Pie con folio y numeración: una hoja de la constancia que se separe del
    # resto tiene que poder identificarse sola. Es lo primero que se pierde
    # cuando alguien imprime, engrapa y desengrapa un expediente.
    pie = (
        '<div style="width:100%;font-size:7pt;color:#8A97A6;padding:0 14mm;'
        'font-family:Helvetica,Arial,sans-serif;display:flex;'
        'justify-content:space-between;">'
        f'<span>Constancia de firma electrónica · Folio {html.escape(doc.get("folio") or "")}</span>'
        '<span>Hoja <span class="pageNumber"></span> de <span class="totalPages"></span></span>'
        '</div>'
    )

    async with async_playwright() as pw:
        navegador = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        pagina = await navegador.new_page()
        await pagina.set_content(html_constancia, wait_until="domcontentloaded")
        await pagina.wait_for_timeout(350)
        pdf_constancia = await pagina.pdf(
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=pie,
            margin={"top": "14mm", "right": "14mm", "bottom": "14mm", "left": "14mm"},
        )
        await navegador.close()

    original = await _bajar_bytes(doc["archivo_ruta"])

    # Las firmas se ponen ENCIMA del original, sin reescribir su texto. El
    # archivo original se conserva intacto en su ruta y su huella no cambia:
    # al final existen dos archivos y dos huellas, el que se leyó y el que se
    # firmó, y la constancia asienta ambas.
    estampado, colocadas = await _estampar(original, doc, firmantes, trazos)

    salida = pypdf.PdfWriter()
    salida.append(pypdf.PdfReader(io.BytesIO(estampado)))
    salida.append(pypdf.PdfReader(io.BytesIO(pdf_constancia)))
    salida.add_metadata({
        "/Title": (doc.get("titulo") or "Documento firmado")[:120],
        "/Producer": "Broquer",
        "/Creator": "Broquer — firma electrónica",
        "/Keywords": f"folio:{doc.get('folio')} sha256-original:{doc.get('hash_original')}",
    })
    buf = io.BytesIO()
    salida.write(buf)
    final = buf.getvalue()

    nombre = _limpio(doc.get("archivo_nombre") or "documento.pdf")
    if nombre.lower().endswith(".pdf"):
        nombre = nombre[:-4]
    ruta = f"{doc['user_id']}/{documento_id}/firmado-{doc.get('folio')}-{nombre}.pdf"
    await _subir_bytes(ruta, final, "application/pdf")

    digest = _sha256(final)
    await _sb_patch("firma_documentos", {"id": f"eq.{documento_id}"}, {
        "firmado_ruta": ruta,
        "hash_firmado": digest,
        "updated_at": _ahora(),
    })
    await evento(doc["user_id"], "sellado",
                 f"Documento armado con su constancia. SHA-256 final: {digest}",
                 documento_id=documento_id, actor="sistema",
                 payload={"sha256_final": digest, "sha256_original": doc.get("hash_original")})


@router.post("/documentos/{documento_id}/sellar")
async def resellar(request: Request, documento_id: str):
    """Reintento manual. Si el armado falló (Chromium caído, Storage lento),
    las firmas siguen intactas en la base y esto vuelve a construir el PDF."""
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    firmantes = await _firmantes(documento_id)
    obligatorios = [f for f in firmantes if f.get("obligatorio", True)]
    if not obligatorios or not all(f.get("estado") == "firmado" for f in obligatorios):
        raise HTTPException(409, "Todavía faltan firmas. El documento se arma cuando firman todos.")
    await _sellar(documento_id)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# DÓNDE VA CADA FIRMA
# ══════════════════════════════════════════════════════════════════════════
# Los contratos dicen "lo firman al margen de cada página y al calce de esta".
# Si las firmas solo viven en la constancia, el documento se contradice solo.
# Y como los agentes suben sus propios machotes, no se puede resolver
# cambiando el texto: hay que dejar que marquen dónde va cada firma.
#
# Las coordenadas van normalizadas de 0 a 1 con el origen arriba a la
# izquierda, igual que se ven en pantalla. Así la misma colocación sirve para
# Carta y para A4, y la vista previa del navegador coincide con el PDF final
# sin importar a qué resolución se haya pintado la hoja.

# A qué resolución se pintan las hojas para colocar los campos. 110 DPI es
# suficiente para leer el contrato en pantalla y pesa la tercera parte que 200.
DPI_VISTA = 110


async def _paginas_a_imagen(doc: dict) -> List[dict]:
    """Convierte cada hoja del PDF en una imagen, una sola vez. A partir de
    ahí la pantalla de colocación abre al instante."""
    import tempfile
    import shutil
    import subprocess
    import glob as _glob

    ya = await _sb_get("firma_paginas", {
        "documento_id": f"eq.{doc['id']}", "select": "*", "order": "pagina.asc"})
    if ya and len(ya) == (doc.get("paginas") or 0):
        return ya

    if not doc.get("archivo_ruta"):
        raise HTTPException(400, "Todavía no hay documento que mostrar.")
    if not shutil.which("pdftoppm"):
        raise HTTPException(503, "El servidor no puede convertir las hojas a imagen. "
                                 "Falta poppler-utils.")

    pdf = await _bajar_bytes(doc["archivo_ruta"])
    carpeta = tempfile.mkdtemp(prefix="firmapag-")
    salida = []
    try:
        entrada = os.path.join(carpeta, "doc.pdf")
        with open(entrada, "wb") as f:
            f.write(pdf)

        r = subprocess.run(
            ["pdftoppm", "-png", "-r", str(DPI_VISTA), entrada,
             os.path.join(carpeta, "hoja")],
            capture_output=True, timeout=120)
        if r.returncode != 0:
            log.error("pdftoppm falló: %s", (r.stderr or b"")[:300])
            raise HTTPException(500, "No se pudieron preparar las hojas del documento.")

        # El tamaño real de cada hoja se saca del PDF, no de la imagen: es lo
        # que hace falta para estampar después en el lugar correcto.
        import pypdf
        lector = pypdf.PdfReader(io.BytesIO(pdf))

        for archivo in sorted(_glob.glob(os.path.join(carpeta, "hoja-*.png"))):
            try:
                num = int(re.search(r"hoja-0*(\d+)\.png$", archivo).group(1))
            except Exception:
                continue
            with open(archivo, "rb") as f:
                png = f.read()

            caja = lector.pages[num - 1].mediabox
            ancho_pt = float(caja.width)
            alto_pt = float(caja.height)

            ruta = f"{doc['user_id']}/{doc['id']}/hoja-{num:03d}.png"
            await _subir_bytes(ruta, png, "image/png")
            filas = await _sb_post("firma_paginas", {
                "user_id": doc["user_id"], "documento_id": doc["id"],
                "pagina": num, "ruta": ruta,
                "ancho_pt": ancho_pt, "alto_pt": alto_pt,
            }, prefer="return=representation,resolution=merge-duplicates")
            salida.append(filas[0] if filas else {
                "pagina": num, "ruta": ruta, "ancho_pt": ancho_pt, "alto_pt": alto_pt})
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)

    salida.sort(key=lambda p: p.get("pagina") or 0)
    return salida


@router.get("/documentos/{documento_id}/paginas")
async def ver_paginas(request: Request, documento_id: str):
    """Las hojas en imagen, con liga firmada, para poder colocar los campos."""
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    paginas = await _paginas_a_imagen(doc)
    salida = []
    for p in paginas:
        try:
            url = await _liga_firmada(p["ruta"], FIRMA_SEGUNDOS)
        except Exception:
            continue
        salida.append({"pagina": p.get("pagina"), "url": url,
                       "ancho_pt": p.get("ancho_pt"), "alto_pt": p.get("alto_pt")})
    return {"paginas": salida, "total": doc.get("paginas")}


class CampoIn(BaseModel):
    firmante_id: str
    pagina: int
    x: float
    y: float
    ancho: float
    alto: float
    tipo: Optional[str] = None


def _acotar(v: float, minimo: float = 0.0, maximo: float = 1.0) -> float:
    return max(minimo, min(maximo, float(v)))


@router.get("/documentos/{documento_id}/campos")
async def listar_campos(request: Request, documento_id: str):
    uid = await _uid(request)
    await _doc_del_usuario(documento_id, uid)
    campos = await _sb_get("firma_campos", {
        "documento_id": f"eq.{documento_id}", "select": "*",
        "order": "pagina.asc,y.asc"})
    return {"campos": campos}


@router.post("/documentos/{documento_id}/campos")
async def crear_campo(request: Request, documento_id: str, body: CampoIn):
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    if doc.get("estado") not in ("borrador",):
        raise HTTPException(409, "Ya no puedes mover las firmas: el documento salió a firma.")

    firmantes = await _sb_get("firma_firmantes", {
        "id": f"eq.{body.firmante_id}", "documento_id": f"eq.{documento_id}",
        "select": "id", "limit": "1"})
    if not firmantes:
        raise HTTPException(404, "Ese firmante no es de este documento.")

    total = doc.get("paginas") or 1
    if body.pagina < 1 or body.pagina > total:
        raise HTTPException(400, f"Ese documento solo tiene {total} páginas.")

    tipo = (body.tipo or "firma").strip()
    if tipo not in ("firma", "rubrica", "nombre", "fecha"):
        tipo = "firma"

    filas = await _sb_post("firma_campos", {
        "user_id": uid, "documento_id": documento_id,
        "firmante_id": body.firmante_id, "pagina": body.pagina, "tipo": tipo,
        "x": _acotar(body.x), "y": _acotar(body.y),
        "ancho": _acotar(body.ancho, 0.02), "alto": _acotar(body.alto, 0.01),
    })
    await _sb_patch("firma_documentos", {"id": f"eq.{documento_id}"},
                    {"campos_colocados": True, "updated_at": _ahora()})
    return {"campo": filas[0] if filas else {}}


@router.delete("/campos/{campo_id}")
async def borrar_campo(request: Request, campo_id: str):
    uid = await _uid(request)
    filas = await _sb_get("firma_campos",
                          {"id": f"eq.{campo_id}", "user_id": f"eq.{uid}",
                           "select": "documento_id", "limit": "1"})
    if not filas:
        raise HTTPException(404, "No encontré ese campo.")
    doc_id = filas[0]["documento_id"]
    await _sb_delete("firma_campos", {"id": f"eq.{campo_id}", "user_id": f"eq.{uid}"})

    quedan = await _sb_get("firma_campos",
                           {"documento_id": f"eq.{doc_id}", "select": "id", "limit": "1"})
    if not quedan:
        await _sb_patch("firma_documentos", {"id": f"eq.{doc_id}"},
                        {"campos_colocados": False, "rubrica_todas": False,
                         "updated_at": _ahora()})
    return {"ok": True}


class RubricarIn(BaseModel):
    firmante_id: Optional[str] = None
    activar: bool = True


@router.post("/documentos/{documento_id}/rubricar-todas")
async def rubricar_todas(request: Request, documento_id: str, body: RubricarIn):
    """Una rúbrica chica al margen de cada hoja, para todos los firmantes.
    Hacerlo a mano en un contrato de nueve hojas sería un martirio, y es
    justo lo que pide el texto de los contratos: "al margen de cada página"."""
    uid = await _uid(request)
    doc = await _doc_del_usuario(documento_id, uid)
    if doc.get("estado") not in ("borrador",):
        raise HTTPException(409, "Ya no puedes mover las firmas: el documento salió a firma.")

    total = doc.get("paginas") or 0
    if total < 1:
        raise HTTPException(400, "Primero sube el PDF.")

    firmantes = await _firmantes(documento_id)
    if body.firmante_id:
        firmantes = [f for f in firmantes if f["id"] == body.firmante_id]
    if not firmantes:
        raise HTTPException(400, "Agrega por lo menos un firmante.")

    # Se limpian las rúbricas anteriores para que no se encimen al repetir.
    await _sb_delete("firma_campos",
                     {"documento_id": f"eq.{documento_id}", "tipo": "eq.rubrica"})

    if not body.activar:
        await _sb_patch("firma_documentos", {"id": f"eq.{documento_id}"},
                        {"rubrica_todas": False, "updated_at": _ahora()})
        return {"ok": True, "creados": 0}

    # Al margen derecho, apiladas hacia arriba desde abajo. Cada firmante
    # tiene su renglón para que no se empalmen.
    ALTO = 0.045
    ANCHO = 0.16
    nuevos = []
    for pagina in range(1, total + 1):
        for i, f in enumerate(firmantes):
            nuevos.append({
                "user_id": uid, "documento_id": documento_id,
                "firmante_id": f["id"], "pagina": pagina, "tipo": "rubrica",
                "x": 0.80,
                "y": 0.90 - (i * (ALTO + 0.012)),
                "ancho": ANCHO, "alto": ALTO,
            })
    if nuevos:
        await _sb_post("firma_campos", nuevos, prefer="return=minimal")

    await _sb_patch("firma_documentos", {"id": f"eq.{documento_id}"},
                    {"rubrica_todas": True, "campos_colocados": True,
                     "updated_at": _ahora()})
    await evento(uid, "documento_creado",
                 f"Se marcó rúbrica al margen en las {total} hojas.",
                 documento_id=documento_id, actor="agente", ip=_ip(request))
    return {"ok": True, "creados": len(nuevos)}


# ══════════════════════════════════════════════════════════════════════════
# VERIFICACIÓN PÚBLICA
# ══════════════════════════════════════════════════════════════════════════
# Sin token y sin sesión: la abre un notario, un abogado o la contraparte que
# recibió el PDF por correo. Devuelve lo justo para confirmar que el documento
# es auténtico, sin filtrar datos personales de nadie.

@router.get("/verificar/{folio}")
async def verificar(folio: str):
    folio = (folio or "").strip().upper()
    if not re.match(r"^BRQ-[A-Z0-9]{8}$", folio):
        raise HTTPException(404, "Ese folio no tiene el formato correcto.")

    docs = await _sb_get("firma_documentos", {"folio": f"eq.{folio}", "select": "*", "limit": "1"})
    if not docs:
        raise HTTPException(404, "No encontramos ningún documento con ese folio.")
    doc = docs[0]
    firmantes = await _firmantes(doc["id"])

    return {
        "existe": True,
        "folio": doc.get("folio"),
        "titulo": doc.get("titulo"),
        "tipo_label": TIPOS.get(doc.get("tipo") or "otro", "Documento"),
        "estado": _resumen_estado(doc, firmantes),
        "paginas": doc.get("paginas"),
        "creado_at": doc.get("created_at"),
        "completado_at": doc.get("completado_at"),
        "hash_original": doc.get("hash_original"),
        "hash_firmado": doc.get("hash_firmado"),
        # Nombre y rol, nada más. Ni teléfonos, ni correos, ni IPs: quien tiene
        # el PDF ya ve esos datos en la constancia; quien solo teclea un folio, no.
        "firmantes": [{
            "nombre": f.get("nombre"),
            "rol_label": ROLES.get(f.get("rol") or "otro", "Firmante"),
            "estado": f.get("estado"),
            "firmado_at": f.get("firmado_at"),
        } for f in firmantes],
        "nom151": bool(doc.get("nom151_folio")),
    }


class PruebaCorreoIn(BaseModel):
    email: str


@router.post("/probar-correo")
async def probar_correo(request: Request, body: PruebaCorreoIn):
    """Manda un correo de prueba y dice exactamente qué pasó. Existe para que
    el agente pueda averiguar si el problema es su configuración SIN tener que
    crear un documento y molestar a un cliente real para descubrirlo."""
    await _uid(request)
    destino = (body.email or "").strip()
    ok, motivo = await _mail(
        destino, "Prueba de correo de Broquer",
        _mail_layout("Tu correo está funcionando",
                     "<p>Si estás leyendo esto, Broquer puede mandarle correos a esta "
                     "dirección. Las invitaciones a firmar van a llegar bien.</p>"))
    return {"ok": ok, "motivo": motivo, "destino": destino, "remitente": RESEND_FROM}


@router.get("/salud")
async def salud():
    ok_pdf = False
    try:
        import pypdf  # noqa: F401
        ok_pdf = True
    except Exception:
        pass
    return {
        "ok": True,
        "supabase": bool(SUPABASE_URL and SUPABASE_SERVICE_KEY),
        "correo": bool(RESEND_API_KEY),
        "plantilla_whatsapp_otp": bool(WA_PLANTILLA_OTP),
        "pypdf": ok_pdf,
        "nivel_maximo": "simple",
    }
