"""Shared helpers for contact import workflows."""
from __future__ import annotations

import unicodedata as _ud

import httpx

from core.database import get_rows


async def map_org_agents(org_id: str, user_id: str) -> dict:
    """Preserve the legacy organization-wide agent matching contract."""
    def _nrm(t):
        t = _ud.normalize("NFD", str(t or ""))
        t = "".join(c for c in t if _ud.category(c) != "Mn")
        return " ".join(t.lower().split())

    por_email, por_nombre = {}, {}
    if not org_id:
        return {"por_email": por_email, "por_nombre": por_nombre, "_nrm": _nrm}
    try:
        try:
            miembros = await get_rows(
                "organizacion_miembros",
                {"org_id": f"eq.{org_id}", "select": "user_id", "limit": "200"},
                timeout=15,
            )
        except httpx.HTTPStatusError:
            miembros = []
        ids = [m["user_id"] for m in miembros if m.get("user_id")]
        if ids:
            try:
                perfiles = await get_rows(
                    "usuarios",
                    {"id": f"in.({','.join(ids)})", "select": "id,nombre,email", "limit": "200"},
                    timeout=15,
                )
            except httpx.HTTPStatusError:
                perfiles = []
            for u in perfiles:
                uid = u.get("id")
                if not uid:
                    continue
                em = (u.get("email") or "").strip().lower()
                if em:
                    por_email[em] = uid
                nm = _nrm(u.get("nombre"))
                if nm:
                    por_nombre[nm] = uid
    except Exception as e:
        print(f"[importar] No se pudo leer el mapa de agentes: {e}")
    return {"por_email": por_email, "por_nombre": por_nombre, "_nrm": _nrm}
