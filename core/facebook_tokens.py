"""Pure Facebook token-expiration state used by backend/UI boundaries."""
from __future__ import annotations

from datetime import datetime, timezone


FACEBOOK_TOKEN_WARNING_DAYS = 14


def facebook_token_state(meta: dict) -> dict:
    """Translate token_expires_at into the exact historical UI status payload."""
    raw = (meta or {}).get("token_expires_at") or ""
    if not raw:
        return {"conocido": False, "dias_restantes": None, "expirado": False,
                "por_expirar": False, "mensaje": ""}
    try:
        venc = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if venc.tzinfo is None:
            venc = venc.replace(tzinfo=timezone.utc)
    except Exception:
        return {"conocido": False, "dias_restantes": None, "expirado": False,
                "por_expirar": False, "mensaje": ""}

    dias = (venc - datetime.now(timezone.utc)).total_seconds() / 86400.0
    dias_int = int(-(-dias // 1)) if dias > 0 else int(dias // 1)
    if dias <= 0:
        msg = ("Tu conexión con Facebook expiró. Reconéctala desde tu perfil o "
               "tus anuncios dejarán de actualizarse.")
    elif dias <= FACEBOOK_TOKEN_WARNING_DAYS:
        msg = (f"Tu conexión con Facebook expira en {max(dias_int, 1)} día(s). "
               f"Reconéctala desde tu perfil para no perder tus campañas de vista.")
    else:
        msg = ""
    return {
        "conocido": True,
        "expira_en": venc.isoformat(),
        "dias_restantes": dias_int,
        "expirado": dias <= 0,
        "por_expirar": 0 < dias <= FACEBOOK_TOKEN_WARNING_DAYS,
        "mensaje": msg,
    }
