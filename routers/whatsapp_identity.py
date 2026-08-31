"""Pure phone-identity helpers shared by WhatsApp domains."""
from __future__ import annotations

import re

from routers.whatsapp_utils import normaliza_mx


def solo_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def es_asesor(numero: dict, wa_id: str) -> bool:
    """Whether a sender is the connected number's owner/personal advisor phone."""
    ajeno = normaliza_mx(wa_id or "")
    if len(ajeno) < 10:
        return False
    for campo in ("numero_personal", "phone_number"):
        propio = normaliza_mx((numero or {}).get(campo) or "")
        if propio and propio[-10:] == ajeno[-10:]:
            return True
    return False
