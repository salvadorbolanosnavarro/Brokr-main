"""Pure helpers shared by the electronic-signature domain.

This module intentionally preserves the historical behavior from
``routers/firmas.py``. It owns no database, storage, HTTP, OTP, or router state.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional


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
