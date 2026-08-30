"""Pure helpers shared by the electronic-signature domain.

This module intentionally preserves the historical behavior from
``routers/firmas.py``. It owns no database, storage, HTTP, OTP, or router state.
"""
from __future__ import annotations

import hashlib
import html
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional


_ALFABETO_FOLIO = "23456789BCDFGHJKMNPQRSTVWXYZ"


def _limpio(nombre: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (nombre or "documento").strip())[:80]
    return base or "documento"


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
