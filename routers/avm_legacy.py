"""Legacy EasyBroker-based AVM extracted from main.py without behavior changes."""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.cache import cache_get, cache_set
from core.easybroker import EB_API_KEY, EB_BASE, eb_headers, extract_colonia


router = APIRouter()


class AVMRequest(BaseModel):
    colonia: str
    ciudad: str
    tipo: str
    operacion: str
    m2_construccion: Optional[float] = None
    m2_terreno: Optional[float] = None
    recamaras: Optional[int] = None
    banos: Optional[float] = None
    estado: Optional[str] = "bueno"
    anio_construccion: Optional[int] = None


def parse_price(val) -> Optional[float]:
    if not val:
        return None
    try:
        v = float(str(val).replace(",", ""))
        if 50_000 <= v <= 999_000_000:
            return v
    except:
        pass
    return None


TIPO_MAP = {
    "casa": ["Casa"],
    "departamento": ["Departamento"],
    "terreno": ["Terreno"],
    "local": ["Local comercial"],
    "comercial": ["Local comercial", "Oficina", "Bodega"],
    "oficina": ["Oficina"],
    "bodega": ["Bodega"],
}
OP_MAP = {"venta": "sale", "renta": "rental"}
TIPO_SIMILAR = {
    "casa": ["Casa", "Departamento"],
    "departamento": ["Departamento", "Casa"],
    "terreno": ["Terreno"],
    "local": ["Local comercial", "Oficina", "Bodega"],
    "comercial": ["Local comercial", "Oficina", "Bodega"],
    "oficina": ["Oficina", "Local comercial"],
    "bodega": ["Bodega", "Local comercial"],
}


async def get_comparables_eb(colonia: str, ciudad: str, tipo: str, operacion: str) -> list:
    cache_key = f"comp_{colonia}_{ciudad}_{tipo}_{operacion}".lower().replace(" ", "_")
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    tipo_labels = TIPO_MAP.get(tipo.lower(), [tipo.capitalize()])
    op_type = OP_MAP.get(operacion.lower(), "sale")
    comparables = []
    page = 1

    def norm(s):
        for a, b in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")]:
            s = s.lower().replace(a, b)
        return re.sub(r"[^a-z0-9 ]", "", s).strip()

    async with httpx.AsyncClient(timeout=60) as client:
        while len(comparables) < 50 and page <= 160:
            r = await client.get(
                f"{EB_BASE}/properties",
                headers=eb_headers(),
                params={"limit": 50, "page": page},
            )
            if r.status_code != 200:
                break
            data = r.json()
            props = data.get("content", [])
            if not props:
                break

            for p in props:
                loc = p.get("location", "")
                if not loc:
                    continue
                if colonia and norm(colonia) not in norm(loc):
                    continue
                if norm(ciudad) not in norm(loc):
                    continue

                prop_type = p.get("property_type", "")
                tipo_match = any(norm(t) in norm(prop_type) for t in tipo_labels)
                if not tipo_match:
                    continue

                ops = p.get("operations", [])
                matching_op = None
                for op in ops:
                    if op.get("type") == op_type:
                        matching_op = op
                        break
                if not matching_op:
                    continue

                created_at = p.get("created_at", "")
                published_at = p.get("published_at", "") or p.get("updated_at", "")
                pub_year = 2026
                if created_at:
                    try:
                        pub_year = int(created_at[:4])
                    except:
                        pass

                price = parse_price(matching_op.get("amount"))
                if not price:
                    continue

                col_prop = extract_colonia(loc)
                comparables.append({
                    "precio": price,
                    "titulo": p.get("title", "")[:80],
                    "m2_construccion": p.get("construction_size"),
                    "m2_terreno": p.get("lot_size"),
                    "recamaras": p.get("bedrooms"),
                    "banos": p.get("bathrooms"),
                    "colonia": col_prop,
                    "fuente": "EasyBroker",
                    "public_id": p.get("public_id", ""),
                    "publicado": created_at[:10] if created_at else (published_at[:10] if published_at else ""),
                    "pub_year": pub_year,
                    "tipo_exacto": norm(tipo_labels[0]) in norm(prop_type),
                })

            if not data.get("pagination", {}).get("next_page"):
                break
            page += 1

    if len(comparables) >= 3:
        prices = sorted(c["precio"] for c in comparables)
        median = prices[len(prices) // 2]
        comparables = [c for c in comparables if median * 0.25 <= c["precio"] <= median * 4.0]

    cache_set(cache_key, comparables[:30])
    return comparables[:30]


APRECIACION_ANUAL = 0.04
ANIO_ACTUAL = 2026


def ajuste_hedonico(comp: dict, sujeto: dict) -> dict:
    precio_base = comp["precio"]
    ajustes = []
    factor = 1.0

    pub_year = comp.get("pub_year", ANIO_ACTUAL)
    anos_transcurridos = max(0, ANIO_ACTUAL - pub_year)
    if anos_transcurridos > 0:
        factor_apreciacion = (1 + APRECIACION_ANUAL) ** anos_transcurridos
        factor *= factor_apreciacion
        ajustes.append(
            f"actualización {anos_transcurridos} año{'s' if anos_transcurridos>1 else ''} "
            f"(+{round((factor_apreciacion-1)*100,1)}% a 4%/año)"
        )

    m2s = sujeto.get("m2_construccion")
    m2c = comp.get("m2_construccion")
    if m2s and m2c and m2c > 0 and abs(m2s - m2c) > 5:
        ratio = (m2s / m2c) ** 0.5
        factor *= ratio
        diff = m2s - m2c
        ajustes.append(f"m² ({'+' if diff>0 else ''}{diff:.0f}): {'+' if ratio>1 else ''}{(ratio-1)*100:.1f}%")

    rs = sujeto.get("recamaras")
    rc = comp.get("recamaras")
    if rs and rc and rs != rc:
        diff = rs - rc
        factor *= (1 + diff * 0.04)
        ajustes.append(f"recámaras ({'+' if diff>0 else ''}{diff}): {'+' if diff>0 else ''}{diff*4}%")

    estado_adj = {"malo": -0.15, "regular": -0.07, "bueno": 0.0, "excelente": 0.08}
    adj_e = estado_adj.get(sujeto.get("estado", "bueno"), 0.0)
    if adj_e != 0:
        factor *= (1 + adj_e)
        ajustes.append(f"estado ({sujeto.get('estado')}): {'+' if adj_e>0 else ''}{adj_e*100:.0f}%")

    anio = sujeto.get("anio_construccion")
    if anio:
        anos = datetime.now().year - anio
        age_adj = max(-0.20, min(0.15, -0.015 * ((anos - 10) / 10)))
        if abs(age_adj) > 0.01:
            factor *= (1 + age_adj)
            ajustes.append(f"antigüedad ({anos} años): {'+' if age_adj>0 else ''}{age_adj*100:.1f}%")

    if not ajustes:
        ajustes.append("sin ajustes — comparable directo")

    return {
        **comp,
        "precio_ajustado": round(precio_base * factor, -3),
        "factor_total": round(factor, 4),
        "ajustes": ajustes,
    }


@router.post("/avm")
async def calcular_avm(req: AVMRequest):
    if not EB_API_KEY:
        raise HTTPException(status_code=500, detail="EB_API_KEY no configurada")

    comparables_raw = await get_comparables_eb(req.colonia, req.ciudad, req.tipo, req.operacion)
    nivel = 1
    nivel_msg = ""

    exact_matches = [c for c in comparables_raw if c.get("tipo_exacto", True)]
    if len(exact_matches) < 3 and req.tipo.lower() in TIPO_SIMILAR:
        similar_tipos = TIPO_SIMILAR[req.tipo.lower()]
        for tipo_alt in similar_tipos[1:]:
            alt_comps = await get_comparables_eb(req.colonia, req.ciudad, tipo_alt.lower(), req.operacion)
            for c in alt_comps:
                if c not in comparables_raw:
                    comparables_raw.append(c)
        if len(comparables_raw) >= 3:
            nivel_msg = (
                f"{len(exact_matches)} comparables exactos en {req.colonia}. "
                f"Se complementó con tipos similares en la misma colonia."
            )

    if len(comparables_raw) < 3:
        nivel = 2
        comparables_raw = await get_comparables_eb("", req.ciudad, req.tipo, req.operacion)
        nivel_msg = (
            f"Pocos comparables en {req.colonia} con datos ene 2025–mar 2026. "
            f"Se amplió a {req.ciudad} — filtrado por precio/m²."
        )

    if len(comparables_raw) < 2:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No se encontraron comparables de {req.tipo} en {req.operacion} "
                f"en {req.ciudad}. Verifica el tipo de operación e inmueble."
            ),
        )

    sujeto = {
        "m2_construccion": req.m2_construccion,
        "m2_terreno": req.m2_terreno,
        "recamaras": req.recamaras,
        "banos": req.banos,
        "estado": req.estado,
        "anio_construccion": req.anio_construccion,
    }

    ajustados = []
    for comp in comparables_raw:
        try:
            ajustados.append(ajuste_hedonico(comp, sujeto))
        except:
            continue

    if not ajustados:
        raise HTTPException(status_code=422, detail="Error procesando comparables")

    if nivel == 2 and req.m2_construccion and req.m2_construccion > 0:
        pm2s = [(c, c["precio_ajustado"] / req.m2_construccion) for c in ajustados]
        if len(pm2s) >= 5:
            vals = sorted(p for _, p in pm2s)
            median_pm2 = vals[len(vals) // 2]
            ajustados = [c for c, pm2 in pm2s if median_pm2 * 0.65 <= pm2 <= median_pm2 * 1.35]

    precios = sorted(c["precio_ajustado"] for c in ajustados)
    n = len(precios)
    trim = max(1, n // 10)
    p_trim = precios[trim:n-trim] if n > 4 else precios

    valor_minimo = round(min(p_trim), -3)
    valor_probable = round(sum(p_trim) / len(p_trim), -3)
    valor_maximo = round(max(p_trim), -3)

    pm2_list = []
    for c in ajustados:
        m2 = c.get("m2_construccion") or req.m2_construccion
        if m2 and m2 > 0:
            pm2_list.append(c["precio_ajustado"] / m2)
    pm2_prom = round(sum(pm2_list) / len(pm2_list)) if pm2_list else None

    nivel_labels = {
        1: f"Alta confianza — {len(ajustados)} comparables en {req.colonia}",
        2: f"Confianza media — {len(ajustados)} comparables en {req.ciudad} (filtrado por precio/m²)",
    }

    return {
        "colonia": req.colonia,
        "ciudad": req.ciudad,
        "tipo": req.tipo,
        "operacion": req.operacion,
        "nivel": nivel,
        "nivel_mensaje": nivel_labels.get(nivel, nivel_msg),
        "fuentes": ["EasyBroker"],
        "num_comparables": len(ajustados),
        "valor_minimo": valor_minimo,
        "valor_probable": valor_probable,
        "valor_maximo": valor_maximo,
        "precio_m2_promedio": pm2_prom,
        "comparables": ajustados[:10],
        "nota": (
            "Valores calculados con base en propiedades publicadas en la bolsa "
            "EasyBroker — comparables actualizados al 2026 con apreciación del 4% anual, más ajustes hedónicos por m², recámaras, "
            "estado y antigüedad. El valor definitivo requiere inspección física "
            "y avalúo formal."
        ),
        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
    }
