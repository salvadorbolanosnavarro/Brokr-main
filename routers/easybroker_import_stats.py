from __future__ import annotations

import re
import uuid as _uuid
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import get_rows, patch_rows, post_rows
from core.easybroker import EB_BASE, _eb_get_reintentos, eb_headers
from routers.easybroker_config import get_eb_key_for_user
from routers.organizaciones import get_org_id_for_user

router = APIRouter()


@router.post("/easybroker/import-stats")
async def easybroker_import_stats(request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    eb_key = await get_eb_key_for_user(user_id)
    if not eb_key:
        raise HTTPException(status_code=400, detail="Configura tu API key de EasyBroker en Perfil → Integración EasyBroker antes de importar.")
    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

    org_id_import = await get_org_id_for_user(user_id)
    filtro_org = ({"org_id": f"eq.{org_id_import}"} if org_id_import else {"user_id": f"eq.{user_id}"})

    prop_por_eb_id = {}
    try:
        propiedades_importadas = await get_rows(
            "propiedades",
            {**filtro_org, "eb_public_id": "not.is.null", "select": "id,eb_public_id", "limit": "5000"},
            timeout=20,
        )
    except httpx.HTTPStatusError:
        propiedades_importadas = []
    for row in propiedades_importadas:
        if row.get("eb_public_id"):
            prop_por_eb_id[row["eb_public_id"]] = row["id"]

    try:
        existentes = await get_rows(
            "contactos",
            {**filtro_org, "select": "id,telefono,email,es_potencial", "limit": "10000"},
            timeout=20,
        )
    except httpx.HTTPStatusError:
        existentes = []

    try:
        vinculos_existentes = await get_rows(
            "contactos_propiedades",
            {"select": "contacto_id,propiedad_id", "relacion": "eq.interes", "limit": "20000"},
            timeout=20,
        )
    except httpx.HTTPStatusError:
        vinculos_existentes = []
    pares_existentes = {(v.get("contacto_id"), v.get("propiedad_id")) for v in vinculos_existentes}

    def _tel_limpio(x):
        return re.sub(r"[^+\d]", "", x or "")[:20]

    por_tel = {_tel_limpio(c.get("telefono")): c for c in existentes if _tel_limpio(c.get("telefono"))}
    por_email = {(c.get("email") or "").strip().lower(): c for c in existentes if c.get("email")}

    solicitudes = []
    pagina = 1
    async with httpx.AsyncClient(timeout=30) as client:
        while pagina <= 400:
            r = await _eb_get_reintentos(
                client,
                f"{EB_BASE}/contact_requests",
                eb_headers(eb_key),
                [("limit", 50), ("page", pagina)],
                timeout=30.0,
            )
            if r is None:
                break
            if r.status_code == 401:
                raise HTTPException(status_code=401, detail="Tu API key de EasyBroker fue rechazada. Reconéctala en Perfil.")
            if r.status_code == 404:
                raise HTTPException(status_code=400, detail="Tu plan de EasyBroker no tiene acceso a solicitudes de contacto vía API.")
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"EasyBroker respondió {r.status_code}: {r.text[:200]}")
            data = r.json()
            items = data.get("content", []) or []
            if not items:
                break
            solicitudes.extend(items)
            if not data.get("pagination", {}).get("next_page"):
                break
            pagina += 1

    total_eb = len(solicitudes)

    def _pid_de(cr):
        return (cr.get("property_public_id") or cr.get("property_id")
                or (cr.get("property") or {}).get("public_id") or "")

    grupos = {}
    sin_datos = 0
    for cr in solicitudes:
        tel = _tel_limpio(cr.get("phone"))
        email = (cr.get("email") or "").strip().lower()[:120]
        nombre = (cr.get("name") or "").strip()[:120]
        if not tel and not email and not nombre:
            sin_datos += 1
            continue
        llave = tel or email or f"nombre:{nombre.lower()}"
        g = grupos.setdefault(llave, {
            "nombre": nombre, "tel": tel, "email": email,
            "fuentes": [], "fechas": [], "props": [], "mensajes": [],
        })
        if nombre and not g["nombre"]:
            g["nombre"] = nombre
        if tel and not g["tel"]:
            g["tel"] = tel
        if email and not g["email"]:
            g["email"] = email
        fuente = (cr.get("source") or "").strip()
        if fuente and fuente not in g["fuentes"]:
            g["fuentes"].append(fuente)
        fecha = cr.get("created_at")
        if fecha:
            g["fechas"].append(fecha)
        pid = _pid_de(cr)
        if pid and pid not in g["props"]:
            g["props"].append(pid)
        msg = (cr.get("message") or "").strip()
        if msg and msg not in g["mensajes"]:
            g["mensajes"].append(msg[:500])

    creados = marcados = ya_estaban = vinculos_nuevos = sin_propiedad = errores = 0
    nuevos_lote: list = []
    ids_marcar: list = []
    vinculos_lote: list = []
    ahora = datetime.utcnow().isoformat()

    for g in grupos.values():
        existente = (por_tel.get(g["tel"]) if g["tel"] else None) or (por_email.get(g["email"]) if g["email"] else None)
        if existente:
            contacto_id = existente["id"]
            if not existente.get("es_potencial"):
                ids_marcar.append(str(contacto_id))
                existente["es_potencial"] = True
            else:
                ya_estaban += 1
        else:
            fecha_real = min(g["fechas"]) if g["fechas"] else ahora
            notas = ""
            if g["mensajes"]:
                notas = ("Mensajes del historial de EasyBroker:\n— " + "\n— ".join(g["mensajes"]))[:2000]
            nuevo = {
                "id": str(_uuid.uuid4()), "user_id": user_id, "org_id": org_id_import,
                "nombre": (g["nombre"] or "Sin nombre").upper()[:120],
                "telefono": g["tel"], "email": g["email"], "tipo": "comprador",
                "es_potencial": True, "estatus": "nuevo",
                "fuente": (g["fuentes"][0] if g["fuentes"] else "EasyBroker")[:80],
                "notas": notas, "created_at": fecha_real, "updated_at": ahora,
            }
            nuevo = {k: v for k, v in nuevo.items() if v not in ("", None, [])}
            nuevos_lote.append(nuevo)
            contacto_id = nuevo["id"]
            if g["tel"]:
                por_tel[g["tel"]] = {"id": contacto_id, "es_potencial": True}
            if g["email"]:
                por_email[g["email"]] = {"id": contacto_id, "es_potencial": True}

        for pid in g["props"]:
            propiedad_id = prop_por_eb_id.get(pid)
            if not propiedad_id:
                sin_propiedad += 1
                continue
            if (contacto_id, propiedad_id) in pares_existentes:
                continue
            vinculos_lote.append({"user_id": user_id, "contacto_id": contacto_id,
                                  "propiedad_id": propiedad_id, "relacion": "interes"})
            pares_existentes.add((contacto_id, propiedad_id))

    ids_creados_ok = set()
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(0, len(nuevos_lote), 100):
            chunk = nuevos_lote[i:i+100]
            try:
                await post_rows("contactos", chunk, prefer="return=minimal", timeout=60,
                                accepted_statuses=(200, 201, 204))
                creados += len(chunk)
                ids_creados_ok.update(c["id"] for c in chunk)
            except httpx.HTTPStatusError:
                errores += len(chunk)

        for i in range(0, len(ids_marcar), 200):
            lote = ids_marcar[i:i+200]
            lista = ",".join(f'"{x}"' for x in lote)
            try:
                await patch_rows("contactos", {"id": f"in.({lista})"},
                                 {"es_potencial": True, "updated_at": ahora}, timeout=60,
                                 accepted_statuses=(200, 204))
                marcados += len(lote)
            except httpx.HTTPStatusError:
                errores += len(lote)

        ids_nuevos_todos = {n["id"] for n in nuevos_lote}
        vinculos_validos = [v for v in vinculos_lote
                            if v["contacto_id"] in ids_creados_ok or v["contacto_id"] not in ids_nuevos_todos]
        for i in range(0, len(vinculos_validos), 200):
            chunk = vinculos_validos[i:i+200]
            try:
                await post_rows("contactos_propiedades", chunk, prefer="return=minimal", timeout=60,
                                accepted_statuses=(200, 201, 204))
                vinculos_nuevos += len(chunk)
            except httpx.HTTPStatusError:
                pass

    return {
        "ok": True, "solicitudes_eb": total_eb, "personas": len(grupos),
        "creados": creados, "marcados": marcados, "ya_estaban": ya_estaban,
        "vinculos": vinculos_nuevos, "sin_propiedad": sin_propiedad,
        "sin_datos": sin_datos, "errores": errores,
    }
