"""Shared Facebook Ads insights vocabulary and normalization."""
from __future__ import annotations


FB_DATE_PRESETS = {
    "today", "yesterday", "this_week_mon_today", "last_week_mon_sun",
    "last_7d", "last_14d", "last_28d", "last_30d", "last_90d",
    "this_month", "last_month", "this_quarter", "last_quarter",
    "this_year", "last_year", "maximum",
}

FB_BREAKDOWNS = {
    "age", "gender", "publisher_platform", "platform_position",
    "impression_device", "region", "country",
}

FB_KEY_ACTIONS = {
    "onsite_conversion.messaging_conversation_started_7d": "conversaciones",
    "onsite_conversion.total_messaging_connection": "mensajes",
    "link_click": "clics_enlace",
    "post_engagement": "engagement",
    "landing_page_view": "vistas_destino",
    "lead": "leads",
    "leadgen_grouped": "leads_formulario",
}

FB_INSIGHTS_FIELDS = (
    "impressions,reach,clicks,ctr,cpc,cpm,spend,frequency,"
    "actions,cost_per_action_type,objective,date_start,date_stop"
)


def normalize_facebook_insights(ins: dict) -> dict:
    """Flatten one Meta insights row into the legacy browser-facing projection."""
    ins = ins or {}

    def _a_mapa(lista) -> dict:
        salida = {}
        for item in (lista or []):
            if not isinstance(item, dict):
                continue
            tipo = item.get("action_type")
            if not tipo:
                continue
            try:
                salida[tipo] = float(item.get("value") or 0)
            except (TypeError, ValueError):
                continue
        return salida

    acciones = _a_mapa(ins.get("actions"))
    costos = _a_mapa(ins.get("cost_per_action_type"))

    out = {
        "impressions": ins.get("impressions", "0"),
        "reach": ins.get("reach", "0"),
        "clicks": ins.get("clicks", "0"),
        "ctr": ins.get("ctr", "0"),
        "cpc": ins.get("cpc", "0"),
        "cpm": ins.get("cpm", "0"),
        "spend": ins.get("spend", "0"),
        "frequency": ins.get("frequency", "0"),
        "date_start": ins.get("date_start", ""),
        "date_stop": ins.get("date_stop", ""),
        "actions": ins.get("actions") or [],
        "cost_per_action_type": ins.get("cost_per_action_type") or [],
    }
    for clave, nombre in FB_KEY_ACTIONS.items():
        out[nombre] = acciones.get(clave, 0)
        out[f"costo_{nombre}"] = costos.get(clave, 0)
    out["engagement"] = out.get("engagement", 0) or acciones.get("post_engagement", 0)
    return out
