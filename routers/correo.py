# ═══════════════════════════════════════════════════════════════════════════
# BROQUER · MÓDULO DE CORREO ELECTRÓNICO
# ═══════════════════════════════════════════════════════════════════════════

import asyncio
import base64
import email
import email.utils
import hashlib
import imaplib
import ipaddress
import re
import smtplib
import socket
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.organizations import get_org_id_for_user
from core.subscriptions import has_paid_feature_access

router = APIRouter()

RESEND_API_KEY = settings.resend_api_key
CORREO_RELAY_FROM = settings.correo_relay_from
PUBLIC_IMAP_PORTS = frozenset({993})
PUBLIC_SMTP_PORTS = frozenset({465, 587})


def _cipher() -> Fernet:
    secreto = settings.require_correo_secret()
    llave = base64.urlsafe_b64encode(hashlib.sha256(secreto.encode()).digest())
    return Fernet(llave)


def _cifrar(texto: str) -> str:
    return _cipher().encrypt(texto.encode()).decode()


def _descifrar(texto: str) -> str:
    return _cipher().decrypt(texto.encode()).decode()


PRESETS = {
    "gmail":   {"imap_host": "imap.gmail.com",         "imap_port": 993,
                "smtp_host": "smtp.gmail.com",          "smtp_port": 465, "smtp_ssl": True},
    "outlook": {"imap_host": "outlook.office365.com",   "imap_port": 993,
                "smtp_host": "smtp.office365.com",      "smtp_port": 587, "smtp_ssl": False},
    "icloud":  {"imap_host": "imap.mail.me.com",        "imap_port": 993,
                "smtp_host": "smtp.mail.me.com",        "smtp_port": 587, "smtp_ssl": False},
}


def _validar_destino_publico(host: str, port: int, *, servicio: str) -> None:
    """Reject local/private/reserved mail destinations before opening sockets."""
    host = (host or "").strip().rstrip(".")
    if not host or len(host) > 253 or any(ch.isspace() for ch in host) or "/" in host or "\\" in host:
        raise ValueError(f"Servidor {servicio} inválido.")
    low = host.lower()
    if low == "localhost" or low.endswith(".localhost") or low.endswith(".local"):
        raise ValueError(f"Servidor {servicio} no permitido.")

    allowed = PUBLIC_IMAP_PORTS if servicio == "IMAP" else PUBLIC_SMTP_PORTS
    if int(port) not in allowed:
        permitidos = ", ".join(str(p) for p in sorted(allowed))
        raise ValueError(f"Puerto {servicio} no permitido. Usa {permitidos}.")

    try:
        direct = ipaddress.ip_address(host)
    except ValueError:
        direct = None
    if direct is not None:
        if not direct.is_global:
            raise ValueError(f"Servidor {servicio} no permitido.")
        return

    try:
        infos = socket.getaddrinfo(host, int(port), family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"No se pudo resolver el servidor {servicio}.") from exc
    addresses = {item[4][0] for item in infos if item and item[4]}
    if not addresses:
        raise ValueError(f"No se pudo resolver el servidor {servicio}.")
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError(f"Servidor {servicio} inválido.") from exc
        if not parsed.is_global:
            raise ValueError(f"Servidor {servicio} no permitido.")


async def _uid(request: Request) -> str:
    return await require_user_id(request, detail="Inicia sesión para continuar.")


async def _suscripcion_activa(user_id: str) -> bool:
    return await has_paid_feature_access(user_id)


async def _uid_max(request: Request) -> str:
    uid = await _uid(request)
    if not await _suscripcion_activa(uid):
        raise HTTPException(402, "El módulo de correo es parte de Broquer Max. Suscríbete para conectar tu correo.")
    return uid


async def _cuenta_de(uid: str) -> Optional[dict]:
    rows = await get_rows("correo_cuentas", {
        "user_id": f"eq.{uid}", "activo": "eq.true", "select": "*", "limit": "1",
    })
    return rows[0] if rows else None


def _imap_conectar(cta: dict) -> imaplib.IMAP4_SSL:
    host = cta["imap_host"]
    port = int(cta["imap_port"] or 993)
    _validar_destino_publico(host, port, servicio="IMAP")
    m = imaplib.IMAP4_SSL(host, port, timeout=15)
    m.login(cta["usuario"], _descifrar(cta["secreto"]))
    return m


def _probar_smtp(host: str, port: int, ssl_directo: bool, usuario: str, password: str) -> Optional[str]:
    try:
        _validar_destino_publico(host, port, servicio="SMTP")
        if ssl_directo:
            s = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            s = smtplib.SMTP(host, port, timeout=15)
            s.starttls()
        s.login(usuario, password)
        s.quit()
        return None
    except Exception as e:
        return f"SMTP (enviar) rechazó la conexión: {e}"


def _probar_conexion(cta: dict) -> Optional[str]:
    try:
        imap_port = int(cta["imap_port"] or 993)
        _validar_destino_publico(cta["imap_host"], imap_port, servicio="IMAP")
        m = imaplib.IMAP4_SSL(cta["imap_host"], imap_port, timeout=15)
        m.login(cta["usuario"], cta["_password_plano"])
        m.logout()
    except Exception as e:
        return f"IMAP (recibir) rechazó la conexión: {e}"

    puerto = int(cta["smtp_port"] or (465 if cta.get("smtp_ssl") else 587))
    error = _probar_smtp(cta["smtp_host"], puerto, bool(cta.get("smtp_ssl")), cta["usuario"], cta["_password_plano"])
    if error is None:
        return None

    alterno_ssl = not bool(cta.get("smtp_ssl"))
    alterno_puerto = 465 if alterno_ssl else 587
    error2 = _probar_smtp(cta["smtp_host"], alterno_puerto, alterno_ssl, cta["usuario"], cta["_password_plano"])
    if error2 is None:
        cta["smtp_port"] = alterno_puerto
        cta["smtp_ssl"] = alterno_ssl
        return None
    if "unreachable" in (error + error2).lower() or "timed out" in (error + error2).lower():
        return ("El servidor de Broquer no pudo salir por los puertos de envío (465 y 587): el hosting los está bloqueando. Recibir correo sí funciona. Detalle: " + error)
    return error


def _decodificar(valor) -> str:
    if not valor:
        return ""
    try:
        return str(make_header(decode_header(valor)))
    except Exception:
        return str(valor)


def _texto_de_mensaje(msg) -> Dict[str, str]:
    texto, html = "", ""
    if msg.is_multipart():
        for parte in msg.walk():
            ctype = parte.get_content_type()
            disp = str(parte.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            try:
                cuerpo = parte.get_payload(decode=True)
                if cuerpo is None:
                    continue
                cuerpo = cuerpo.decode(parte.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                continue
            if ctype == "text/plain" and not texto:
                texto = cuerpo
            elif ctype == "text/html" and not html:
                html = cuerpo
    else:
        try:
            cuerpo = msg.get_payload(decode=True)
            cuerpo = cuerpo.decode(msg.get_content_charset() or "utf-8", errors="replace") if cuerpo else ""
        except Exception:
            cuerpo = ""
        if msg.get_content_type() == "text/html":
            html = cuerpo
        else:
            texto = cuerpo
    return {"texto": texto, "html": html}


def _snippet(texto: str, html: str) -> str:
    base = texto or re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", base).strip()[:140]


def _listar_bandeja(cta: dict, limite: int, carpeta: str) -> List[dict]:
    m = _imap_conectar(cta)
    try:
        m.select(carpeta, readonly=True)
        ok, data = m.uid("search", None, "ALL")
        uids = (data[0] or b"").split()
        uids = uids[-limite:][::-1]
        out = []
        for uid in uids:
            ok, msgdata = m.uid("fetch", uid, "(FLAGS BODY.PEEK[])")
            if ok != "OK" or not msgdata or msgdata[0] is None:
                continue
            flags = b" ".join(p for p in msgdata if isinstance(p, bytes))
            visto = b"\\Seen" in flags
            crudo = None
            for p in msgdata:
                if isinstance(p, tuple) and len(p) >= 2:
                    crudo = p[1]
                    break
            if crudo is None:
                continue
            msg = email.message_from_bytes(crudo)
            partes = _texto_de_mensaje(msg)
            fecha = ""
            try:
                dt = email.utils.parsedate_to_datetime(msg.get("Date"))
                fecha = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass
            out.append({
                "uid": uid.decode(), "de": _decodificar(msg.get("From")), "para": _decodificar(msg.get("To")),
                "asunto": _decodificar(msg.get("Subject")) or "(sin asunto)", "fecha": fecha,
                "visto": visto, "snippet": _snippet(partes["texto"], partes["html"]),
            })
        return out
    finally:
        try:
            m.logout()
        except Exception:
            pass


def _leer_mensaje(cta: dict, uid: str, carpeta: str) -> Optional[dict]:
    m = _imap_conectar(cta)
    try:
        m.select(carpeta)
        ok, msgdata = m.uid("fetch", uid.encode(), "(BODY[])")
        if ok != "OK" or not msgdata or msgdata[0] is None:
            return None
        crudo = None
        for p in msgdata:
            if isinstance(p, tuple) and len(p) >= 2:
                crudo = p[1]
                break
        if crudo is None:
            return None
        msg = email.message_from_bytes(crudo)
        partes = _texto_de_mensaje(msg)
        fecha = ""
        try:
            dt = email.utils.parsedate_to_datetime(msg.get("Date"))
            fecha = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
        return {
            "uid": uid, "de": _decodificar(msg.get("From")), "para": _decodificar(msg.get("To")),
            "asunto": _decodificar(msg.get("Subject")) or "(sin asunto)", "fecha": fecha,
            "texto": partes["texto"], "html": partes["html"],
            "message_id": msg.get("Message-ID") or "", "references": msg.get("References") or "",
        }
    finally:
        try:
            m.logout()
        except Exception:
            pass


def _enviar_smtp(cta: dict, para: str, asunto: str, cuerpo: str, in_reply_to: str = "", references: str = "") -> None:
    msg = MIMEMultipart("alternative")
    msg["From"] = cta["email"]
    msg["To"] = para
    msg["Subject"] = asunto
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (references + " " + in_reply_to).strip()
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    password = _descifrar(cta["secreto"])
    host = cta["smtp_host"]
    port = int(cta["smtp_port"] or (465 if cta.get("smtp_ssl") else 587))
    _validar_destino_publico(host, port, servicio="SMTP")
    if cta.get("smtp_ssl"):
        s = smtplib.SMTP_SSL(host, port, timeout=20)
    else:
        s = smtplib.SMTP(host, port, timeout=20)
        s.starttls()
    try:
        s.login(cta["usuario"], password)
        s.sendmail(cta["email"], [d.strip() for d in para.split(",") if d.strip()], msg.as_string())
    finally:
        try:
            s.quit()
        except Exception:
            pass


class ConectarReq(BaseModel):
    email: str
    password: str
    proveedor: str = ""
    imap_host: str = ""
    imap_port: int = 0
    smtp_host: str = ""
    smtp_port: int = 0
    smtp_ssl: Optional[bool] = None


@router.get("/correo/estado")
async def correo_estado(request: Request):
    uid = await _uid(request)
    cta = await _cuenta_de(uid)
    if not cta:
        return {"conectado": False, "presets": list(PRESETS.keys())}
    return {"conectado": True, "email": cta["email"], "imap_host": cta["imap_host"], "smtp_host": cta["smtp_host"]}


@router.post("/correo/conectar")
async def correo_conectar(req: ConectarReq, request: Request):
    uid = await _uid_max(request)
    correo = (req.email or "").strip().lower()
    password = (req.password or "").strip()
    if "@" not in correo or not password:
        raise HTTPException(400, "Captura tu correo y tu contraseña de aplicación.")

    preset = PRESETS.get((req.proveedor or "").lower(), {})
    cta = {
        "email": correo, "usuario": correo,
        "imap_host": (req.imap_host or "").strip() or preset.get("imap_host", ""),
        "imap_port": req.imap_port or preset.get("imap_port", 993),
        "smtp_host": (req.smtp_host or "").strip() or preset.get("smtp_host", ""),
        "smtp_port": req.smtp_port or preset.get("smtp_port", 587),
        "smtp_ssl": req.smtp_ssl if req.smtp_ssl is not None else preset.get("smtp_ssl", False),
        "_password_plano": password,
    }
    if not cta["imap_host"] or not cta["smtp_host"]:
        raise HTTPException(400, "Falta el servidor IMAP o SMTP. Elige un proveedor o captúralos manualmente.")
    try:
        await asyncio.to_thread(_validar_destino_publico, cta["imap_host"], int(cta["imap_port"]), servicio="IMAP")
        await asyncio.to_thread(_validar_destino_publico, cta["smtp_host"], int(cta["smtp_port"]), servicio="SMTP")
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc

    error = await asyncio.to_thread(_probar_conexion, cta)
    aviso = ""
    if error:
        es_bloqueo_red = "no pudo salir por los puertos" in error
        if es_bloqueo_red and RESEND_API_KEY:
            aviso = ("Tu bandeja quedó conectada. El envío saldrá por el servidor de Broquer a nombre de " +
                     CORREO_RELAY_FROM + " con respuestas dirigidas a tu correo, porque el hosting bloquea el envío directo.")
        else:
            raise HTTPException(400, error)

    ahora = datetime.now(timezone.utc).isoformat()
    fila = {
        "user_id": uid, "email": cta["email"], "usuario": cta["usuario"],
        "imap_host": cta["imap_host"], "imap_port": cta["imap_port"],
        "smtp_host": cta["smtp_host"], "smtp_port": cta["smtp_port"], "smtp_ssl": cta["smtp_ssl"],
        "secreto": _cifrar(password), "activo": True, "updated_at": ahora,
    }
    try:
        fila["org_id"] = await get_org_id_for_user(uid)
    except Exception as exc:
        raise HTTPException(503, "No se pudo verificar tu organización.") from exc

    existente = await get_rows("correo_cuentas", {"user_id": f"eq.{uid}", "select": "id", "limit": "1"})
    if existente:
        await patch_rows("correo_cuentas", {"user_id": f"eq.{uid}"}, fila)
    else:
        fila["created_at"] = ahora
        try:
            await post_rows("correo_cuentas", fila)
        except Exception as exc:
            raise HTTPException(502, "No se pudo guardar la cuenta. Corre la migración migracion-correo.sql.") from exc
    return {"ok": True, "email": correo, "aviso": aviso}


@router.delete("/correo/desconectar")
async def correo_desconectar(request: Request):
    uid = await _uid(request)
    await delete_rows("correo_cuentas", {"user_id": f"eq.{uid}"})
    return {"ok": True}


@router.get("/correo/bandeja")
async def correo_bandeja(request: Request, limite: int = 30, carpeta: str = "INBOX"):
    uid = await _uid(request)
    cta = await _cuenta_de(uid)
    if not cta:
        raise HTTPException(404, "No tienes un correo conectado.")
    limite = max(1, min(int(limite or 30), 50))
    try:
        mensajes = await asyncio.to_thread(_listar_bandeja, cta, limite, carpeta)
    except Exception as e:
        raise HTTPException(502, f"No se pudo leer la bandeja: {e}")
    return {"ok": True, "email": cta["email"], "mensajes": mensajes}


@router.get("/correo/mensaje/{uid_msg}")
async def correo_mensaje(uid_msg: str, request: Request, carpeta: str = "INBOX"):
    uid = await _uid(request)
    cta = await _cuenta_de(uid)
    if not cta:
        raise HTTPException(404, "No tienes un correo conectado.")
    if not re.fullmatch(r"[0-9]+", uid_msg or ""):
        raise HTTPException(400, "Mensaje no válido.")
    try:
        msg = await asyncio.to_thread(_leer_mensaje, cta, uid_msg, carpeta)
    except Exception as e:
        raise HTTPException(502, f"No se pudo leer el mensaje: {e}")
    if not msg:
        raise HTTPException(404, "El mensaje ya no está en esta carpeta.")
    return {"ok": True, "mensaje": msg}


class EnviarReq(BaseModel):
    para: str
    asunto: str
    cuerpo: str
    in_reply_to: str = ""
    references: str = ""


@router.post("/correo/enviar")
async def correo_enviar(req: EnviarReq, request: Request):
    uid = await _uid_max(request)
    cta = await _cuenta_de(uid)
    if not cta:
        raise HTTPException(404, "No tienes un correo conectado.")
    para = (req.para or "").strip()
    asunto = (req.asunto or "").strip()[:300]
    cuerpo = (req.cuerpo or "").strip()
    if "@" not in para or not cuerpo:
        raise HTTPException(400, "Captura el destinatario y el mensaje.")
    try:
        await asyncio.to_thread(_enviar_smtp, cta, para, asunto, cuerpo, req.in_reply_to or "", req.references or "")
        return {"ok": True, "via": "smtp"}
    except Exception as e:
        bloqueo_red = "unreachable" in str(e).lower() or "timed out" in str(e).lower()
        if not (bloqueo_red and RESEND_API_KEY):
            raise HTTPException(502, f"No se pudo enviar: {e}")

    import html as _html
    cuerpo_html = "<p>" + _html.escape(cuerpo).replace("\n", "<br>") + "</p>"
    payload = {
        "from": f"{cta['email']} vía Broquer <{CORREO_RELAY_FROM}>",
        "to": [d.strip() for d in para.split(",") if d.strip()], "reply_to": cta["email"],
        "subject": asunto, "html": cuerpo_html, "text": cuerpo,
    }
    if req.in_reply_to:
        payload["headers"] = {"In-Reply-To": req.in_reply_to, "References": ((req.references or "") + " " + req.in_reply_to).strip()}
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post("https://api.resend.com/emails",
                         headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                         json=payload)
    if r.status_code not in (200, 201, 202):
        try:
            detalle = (r.json() or {}).get("message") or r.text[:200]
        except Exception:
            detalle = r.text[:200]
        raise HTTPException(502, f"No se pudo enviar (relay): {detalle}")
    return {"ok": True, "via": "relay"}
