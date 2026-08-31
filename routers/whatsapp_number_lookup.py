"""Exact WhatsApp number lookup core."""


async def _get_numero_core(phone_number_id: str, *, sb_get) -> dict | None:
    rows = await sb_get("wa2_numeros", {"phone_number_id": f"eq.{phone_number_id}", "select": "*", "limit": "1"})
    return rows[0] if rows else None
