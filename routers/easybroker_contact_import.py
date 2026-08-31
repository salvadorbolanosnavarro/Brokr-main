from __future__ import annotations

import asyncio
import re
import time
import uuid as _uuid
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.contact_import import map_org_agents
from core.database import get_rows, patch_rows, post_rows
from core.easybroker import EB_BASE, _EB_LOTE, _EB_PAUSA_LOTE, _eb_get_reintentos, eb_headers
from core.easybroker_migration import set_import_progress
from routers.easybroker_config import get_eb_key_for_user
from routers.organizaciones import get_org_id_for_user


router = APIRouter()


@router.post("/contactos/importar-eb")
async def importar_contactos_eb(request: Request):
    """Import EasyBroker contacts while preserving the legacy merge contract."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")

    eb_key = await get_eb_key_for_user(user_id)
    if not eb_key:
        raise HTTPException(status_code=400, detail="No tienes una API Key de EasyBroker configurada. Ve a Configuración → Integraciones.")

    org_id_import = await get_org_id_for_user(user_id)
    filtro_existentes = ({"org_id": f"eq.{org_id_import}"} if org_id_import
                         else {"user_id": f"eq.{user_id}"})
    try:
        existing = await get_rows(
            "contactos",
            {**filtro_existentes,
             "select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas"},
            timeout=15,
        )
    except httpx.HTTPStatusError:
        existing = []
    existing_by_tel = {c["telefono"]: c for c in existing if c.get("telefono")}
    existing_by_email = {c["email"]: c for c in existing if c.get("email")}

    importados = 0
    actualizados = 0
    omitidos = 0
    errores = 0
    total_eb = 0
    page = 1

    _PROB = {"low": "baja", "medium": "media", "high": "alta"}

    def _tel_wa(c):
        tel, wa = "", ""
        for p in (c.get("phones") or []):
            num = re.sub(r"[^+\d]", "", p.get("phone") or "")
            if not num:
                continue
            t = (p.get("type") or "").lower()
            if t == "whatsapp" and not wa:
                wa = num
            if not tel or t in ("mobile", "whatsapp"):
                tel = num
        return tel[:20], wa[:20]

    def _first_email(c):
        for e in (c.get("emails") or []):
            if e.get("email"):
                return e["email"].strip().lower()[:120]
        return ""

    mapa_ag = await map_org_agents(org_id_import, user_id)

    def _user_de_agente_eb(c):
        ag = c.get("agent") or {}
        em = (ag.get("email") or "").strip().lower()
        if em and em in mapa_ag["por_email"]:
            return mapa_ag["por_email"][em]
        for llave in ("full_name", "name"):
            nm = mapa_ag["_nrm"](ag.get(llave))
            if nm and nm in mapa_ag["por_nombre"]:
                return mapa_ag["por_nombre"][nm]
        return None

    def _mapear(c):
        nombre = (c.get("full_name")
                  or " ".join(x for x in [c.get("first_name"), c.get("last_name")] if x)
                  or "").strip()[:120]
        tel, wa = _tel_wa(c)
        dirs = c.get("addresses") or []
        dom = dirs[0] if dirs else {}
        return {
            "nombre": nombre,
            "telefono": tel,
            "wa": wa,
            "email": _first_email(c),
            "empresa": (c.get("company") or "")[:120],
            "notas": (c.get("private_description") or "")[:2000],
            "etiquetas": [t for t in (c.get("tags") or []) if t][:40],
            "fuente": (c.get("source") or None),
            "probabilidad": _PROB.get((c.get("probability") or "").lower()),
            "calle": (dom.get("street") or "")[:160],
            "mpio": (dom.get("city") or "")[:80],
            "cp": (dom.get("postal_code") or "")[:12],
        }

    eb_ids = []
    async with httpx.AsyncClient(timeout=20) as client:
        while True:
            r = await _eb_get_reintentos(
                client,
                f"{EB_BASE}/contacts",
                eb_headers(eb_key),
                {"page": page, "limit": 50},
            )
            if r is None:
                raise HTTPException(status_code=502, detail="EasyBroker no respondió tras varios intentos. Espera un minuto y vuelve a intentar.")
            if r.status_code == 404:
                raise HTTPException(status_code=400, detail="Tu plan de EasyBroker no tiene acceso a contactos vía API, o el endpoint no está disponible.")
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"EasyBroker respondió {r.status_code}: {r.text[:300]}")
            data = r.json()
            items = data.get("content", data.get("data", [])) or []
            if not items:
                break
            for it in items:
                cid = it.get("id")
                if cid is not None:
                    eb_ids.append(cid)
            pagination = data.get("pagination", {})
            if len(items) < 50 or not pagination.get("next_page"):
                break
            page += 1

    total_eb = len(eb_ids)

    async def _detalle(client, cid):
        try:
            rd = await _eb_get_reintentos(
                client, f"{EB_BASE}/contacts/{cid}", eb_headers(eb_key))
            if rd is not None and rd.status_code == 200:
                return rd.json()
        except Exception:
            pass
        return None

    detalles = []
    lotes_fallidos_seguidos = 0
    async with httpx.AsyncClient(timeout=20) as client:
        for i in range(0, len(eb_ids), _EB_LOTE):
            lote = eb_ids[i:i + _EB_LOTE]
            set_import_progress(user_id, f"contactos {min(i + _EB_LOTE, len(eb_ids))} de {len(eb_ids)}")
            inicio_lote = time.monotonic()
            res = await asyncio.gather(*[_detalle(client, cid) for cid in lote])
            buenos = [d for d in res if d]
            detalles.extend(buenos)
            resto = _EB_PAUSA_LOTE - (time.monotonic() - inicio_lote)
            if resto > 0 and i + _EB_LOTE < len(eb_ids):
                await asyncio.sleep(resto)
            lotes_fallidos_seguidos = (lotes_fallidos_seguidos + 1 if not buenos else 0)
            if lotes_fallidos_seguidos >= 4:
                raise HTTPException(status_code=429, detail="EasyBroker está limitando las peticiones de tu cuenta (429 sostenido). Espera 10-15 minutos y vuelve a correr la migración: lo ya importado no se pierde ni se duplica.")

    async with httpx.AsyncClient(timeout=20) as client:
        for _idx_c, c in enumerate(detalles):
            if _idx_c % 25 == 0:
                set_import_progress(user_id, f"guardando contactos {_idx_c} de {len(detalles)}")
            m = _mapear(c)
            if not m["nombre"] and not m["telefono"] and not m["email"]:
                omitidos += 1
                continue

            now_iso = datetime.utcnow().isoformat()
            existente = existing_by_tel.get(m["telefono"]) or existing_by_email.get(m["email"])

            if existente:
                patch = {}
                for campo in ("nombre", "telefono", "email", "wa", "empresa",
                              "notas", "fuente", "probabilidad", "calle", "mpio", "cp"):
                    if not existente.get(campo) and m.get(campo):
                        patch[campo] = m[campo]
                if m["etiquetas"]:
                    prev = existente.get("etiquetas") or []
                    union = list(dict.fromkeys([*prev, *m["etiquetas"]]))
                    if union != prev:
                        patch["etiquetas"] = union
                if patch:
                    patch["updated_at"] = now_iso
                    filtro_patch = ({"org_id": f"eq.{org_id_import}"} if org_id_import
                                    else {"user_id": f"eq.{user_id}"})
                    try:
                        await patch_rows(
                            "contactos",
                            {"id": f"eq.{existente['id']}", **filtro_patch},
                            patch,
                            timeout=20,
                            accepted_statuses=(200, 204),
                        )
                        actualizados += 1
                    except httpx.HTTPStatusError:
                        errores += 1
                else:
                    omitidos += 1
            else:
                nuevo = {
                    "id": str(_uuid.uuid4()),
                    "user_id": _user_de_agente_eb(c) or user_id,
                    "org_id": org_id_import,
                    "tipo": "otro",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    **m,
                }
                nuevo["nombre"] = m["nombre"] or "Sin nombre"
                nuevo = {k: v for k, v in nuevo.items() if v not in ("", None, [])}
                try:
                    await post_rows(
                        "contactos",
                        nuevo,
                        prefer="return=minimal",
                        timeout=20,
                        accepted_statuses=(200, 201),
                    )
                    importados += 1
                    if m["telefono"]:
                        existing_by_tel[m["telefono"]] = nuevo
                    if m["email"]:
                        existing_by_email[m["email"]] = nuevo
                except httpx.HTTPStatusError:
                    errores += 1

    return {
        "ok": True,
        "total": total_eb,
        "importados": importados,
        "actualizados": actualizados,
        "omitidos": omitidos,
        "errores": errores,
    }
