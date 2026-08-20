"""Legacy admin usage/cost aggregation extracted from main.py."""
from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from core.config import settings
from core.database import get_rows
from core.legacy_admin import require_legacy_admin


router = APIRouter()


@router.get("/admin/user/{user_id}/uso")
async def admin_user_uso(user_id: str, request: Request, dias: int = 30):
    """Aggregate AI usage/cost and module time for an admin-selected user."""
    await require_legacy_admin(request)
    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(status_code=500, detail="Supabase no está configurado.")

    try:
        dias_int = max(1, min(int(dias), 365))
    except Exception:
        dias_int = 30
    desde_iso = (datetime.utcnow() - timedelta(days=dias_int)).isoformat() + "Z"

    usage_rows: List[Dict[str, Any]] = []
    try:
        usage_rows = await get_rows(
            "usage_logs",
            {
                "user_id": f"eq.{user_id}",
                "ts": f"gte.{desde_iso}",
                "select": "modulo,herramienta,proveedor,modelo,tokens_in,tokens_out,unidades,costo_usd,ts",
                "order": "ts.desc",
                "limit": "20000",
            },
            timeout=15,
        )
    except Exception:
        usage_rows = []

    session_rows: List[Dict[str, Any]] = []
    try:
        session_rows = await get_rows(
            "module_sessions",
            {
                "user_id": f"eq.{user_id}",
                "ts": f"gte.{desde_iso}",
                "select": "modulo,segundos,ts",
                "limit": "50000",
            },
            timeout=15,
        )
    except Exception:
        session_rows = []

    por_modulo: Dict[str, Dict[str, Any]] = {}
    for row in session_rows:
        m = row.get("modulo") or "desconocido"
        slot = por_modulo.setdefault(
            m,
            {"modulo": m, "segundos": 0, "costo_usd": 0.0, "llamadas": 0},
        )
        slot["segundos"] += int(row.get("segundos") or 0)
    for row in usage_rows:
        m = row.get("modulo") or "desconocido"
        slot = por_modulo.setdefault(
            m,
            {"modulo": m, "segundos": 0, "costo_usd": 0.0, "llamadas": 0},
        )
        slot["costo_usd"] += float(row.get("costo_usd") or 0)
        slot["llamadas"] += 1

    por_herramienta: Dict[str, Dict[str, Any]] = {}
    for row in usage_rows:
        key = f"{row.get('herramienta','')}|{row.get('proveedor','')}|{row.get('modelo','')}"
        slot = por_herramienta.setdefault(
            key,
            {
                "herramienta": row.get("herramienta") or "",
                "proveedor": row.get("proveedor") or "",
                "modelo": row.get("modelo") or "",
                "llamadas": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "unidades": 0,
                "costo_usd": 0.0,
            },
        )
        slot["llamadas"] += 1
        slot["tokens_in"] += int(row.get("tokens_in") or 0)
        slot["tokens_out"] += int(row.get("tokens_out") or 0)
        slot["unidades"] += int(row.get("unidades") or 0)
        slot["costo_usd"] += float(row.get("costo_usd") or 0)

    costo_total = round(sum(float(r.get("costo_usd") or 0) for r in usage_rows), 4)
    tiempo_total = sum(int(r.get("segundos") or 0) for r in session_rows)
    llamadas_total = len(usage_rows)

    modulos_arr = []
    for slot in por_modulo.values():
        modulos_arr.append(
            {
                "modulo": slot["modulo"],
                "segundos": int(slot["segundos"]),
                "costo_usd": round(float(slot["costo_usd"]), 4),
                "llamadas": int(slot["llamadas"]),
            }
        )
    modulos_arr.sort(key=lambda x: (x["segundos"], x["costo_usd"]), reverse=True)

    herramientas_arr = []
    for slot in por_herramienta.values():
        herramientas_arr.append({**slot, "costo_usd": round(float(slot["costo_usd"]), 4)})
    herramientas_arr.sort(key=lambda x: (x["costo_usd"], x["llamadas"]), reverse=True)

    return {
        "ok": True,
        "user_id": user_id,
        "dias": dias_int,
        "desde": desde_iso,
        "totales": {
            "segundos": tiempo_total,
            "llamadas": llamadas_total,
            "costo_usd": costo_total,
        },
        "por_modulo": modulos_arr,
        "por_herramienta": herramientas_arr,
    }
