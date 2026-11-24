"""Modo en vivo: valuar HOY, sin modelo entrenado ni datos acumulados.

1. Busca y lee anuncios reales de la zona en ese momento, con el mismo buscador
   y lector del AVM actual (routers/avm_websearch.py). Firecrawl devuelve los
   anuncios ya estructurados (precio, m², recámaras…); aquí solo se leen.
2. Ubica cada anuncio, lo limpia y quita duplicados con las mismas reglas del
   modelo.
3. Calcula con los dos motores que no necesitan entrenamiento:
   A · comparables homologados y C · enfoque físico. Todo en Python.
4. La incertidumbre sale de los propios comparables de hoy (qué tan dispersos
   están después de homologar) y de cuánto discrepan A y C. El rango NO está
   calibrado con cierres todavía, y la respuesta lo dice.
5. Cada anuncio leído se guarda en avm_listings: cada valuación también junta
   datos para el modelo entrenado.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from . import geo
from . import settings as S
from .contexto import Contexto, ciudad_mas_cercana
from .engines.motor_a_comparables import MotorA
from .engines.motor_c_fisico import MotorC
from .ensemble import TablaDelta, delta_extra_por_dias, ensamblar
from .etl import clean, dedupe
from .features import preparar
from .indice import IndicePrecios

log = logging.getLogger("broquer.avm_v2.en_vivo")
TIPO_BUSQUEDA = {"casa": "casa", "depto": "departamento", "terreno": "terreno", "local": "local"}
SIGMA_C_SIN_CALIBRAR = 0.25     # enfoque físico sin validar en la zona
SIGMA_A_MINIMO = 0.08           # piso: ni con comparables idénticos hay certeza total
ESTADOS = {c["nombre"]: c["estado"] for c in S.ciudades()}


class SinComparables(Exception):
    """No se encontraron suficientes anuncios reales hoy en la zona."""


async def _leer_anuncios(sujeto: dict, ciudad: str, estado: str) -> list[dict]:
    """Busca y lee páginas de portales con el pipeline del AVM actual."""
    from routers.avm_websearch import (AvmWebSearchRequest, _collect_search_candidates, _colonias_vecinas,
                                       _fetch_candidate_pages)
    from .etl.ingest_listings import parsear_bloque, parsear_json_ld

    tipo = sujeto["tipo"]
    req = AvmWebSearchRequest(
        colonia=sujeto.get("colonia") or "", tipo_inmueble=TIPO_BUSQUEDA[tipo], operacion="venta",
        m2_construccion=float(sujeto.get("m2_construidos") or 0), m2_terreno=float(sujeto.get("m2_terreno") or 0),
        recamaras=int(sujeto.get("recamaras") or 0), banos=float(sujeto.get("banos") or 0),
        ciudad=ciudad or "", estado=estado or "", latitud=float(sujeto["lat"]), longitud=float(sujeto["lon"]),
    )
    vecinas = await _colonias_vecinas(req.latitud, req.longitud, req.colonia)
    busqueda = await _collect_search_candidates(req, vecinas)
    paginas = await _fetch_candidate_pages(busqueda["results"], colonia=req.colonia, ciudad=req.ciudad)
    anuncios, vistos = [], set()
    for p in paginas:
        texto = p.get("page_text") or ""
        for a in parsear_bloque(texto, tipo) or parsear_json_ld(texto, p.get("url", ""), tipo):
            if a["url"] in vistos:
                continue
            vistos.add(a["url"])
            anuncios.append(a)
    return anuncios


async def _ubicar(anuncios: list[dict], ciudad: str, estado: str) -> None:
    """Geocodifica por la ubicación que trae cada anuncio (colonia o calle).
    Una sola consulta por texto distinto."""
    from .service import UbicacionAmplia, geocodificar
    cache: dict[str, tuple | None] = {}
    for a in anuncios:
        texto = (a.get("ubicacion") or "").strip()
        if not texto:
            continue
        consulta = f"{texto}, {ciudad}, {estado}" if ciudad and ciudad.lower() not in texto.lower() else texto
        if consulta not in cache:
            try:
                cache[consulta] = await geocodificar(consulta)
            except UbicacionAmplia:
                cache[consulta] = None     # solo dice la ciudad: no sirve como comparable
        g = cache[consulta]
        if g:
            a["lat"], a["lon"], a["precision_ubicacion"] = g[0], g[1], g[2]
            a["colonia"] = texto.split(",")[0][:120]


def _a_tabla(anuncios: list[dict], ciudad: str) -> pd.DataFrame:
    hoy = pd.Timestamp(date.today())
    filas = []
    for i, a in enumerate(anuncios, 1):
        if a.get("lat") is None:
            continue
        filas.append({
            "id": -i, "url": a["url"], "fuente": a.get("fuente"), "tipo": a["tipo"], "operacion": a["operacion"],
            "precio": a["precio"], "moneda": a.get("moneda") or "MXN",
            "m2_construidos": a.get("m2_construidos"), "m2_terreno": a.get("m2_terreno"),
            "recamaras": a.get("recamaras"), "banos": a.get("banos"), "estacionamientos": a.get("estacionamientos"),
            "lat": a["lat"], "lon": a["lon"], "precision_ubicacion": a.get("precision_ubicacion", "aproximada"),
            "colonia": a.get("colonia"), "descripcion": a.get("titulo"),
            "ciudad": ciudad, "municipio": ciudad, "zona_indice": ciudad,
            "fecha_alta": hoy, "ultimo_visto": hoy,
        })
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    for c in ("m2_construidos", "m2_terreno", "recamaras", "banos", "estacionamientos"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for r in (7, 8, 9):
        df[f"h3_{r}"] = geo.celdas(df["lat"], df["lon"], r)
    return df


def _contexto() -> Contexto:
    from .synthetic import agebs_contexto
    ageb = agebs_contexto()
    return Contexto(ageb if ageb is not None else None)


def _explicacion(res_a, res_c, colonia: str | None) -> list[str]:
    out = []
    if res_a.ok:
        comps = res_a.comparables
        dist = int(np.median([c["dist_m"] for c in comps]))
        pm2 = float(np.exp(res_a.ln_pm2))
        out.append(f"Se compararon {len(comps)} anuncios en venta leídos hoy, a una distancia típica de "
                   f"{dist:,} m del inmueble.")
        out.append(f"Después de ajustarlos por tamaño, edad, conservación y ubicación, el precio por m² "
                   f"homologado es de ${pm2:,.0f}.")
        fact = np.array([c["factor_total"] for c in comps])
        if abs(np.median(fact) - 1) >= 0.03:
            sentido = "más" if np.median(fact) > 1 else "menos"
            out.append(f"Frente a los comparables, este inmueble vale alrededor de "
                       f"{abs(np.median(fact) - 1) * 100:.0f} % {sentido} por sus características.")
    if res_c.ok:
        d = res_c.detalle
        out.append(f"Por enfoque físico: terreno ${d['valor_terreno']:,.0f} (suelo a ${d['vu_suelo']:,.0f}/m², "
                   f"de {d['origen_suelo']}) más construcción depreciada ${d['valor_construccion']:,.0f}.")
    return out[:5]


async def estimar(sujeto: dict) -> dict:
    """sujeto: tipo, lat, lon, m2_construidos, m2_terreno, recamaras, banos,
    edad_anios, conservacion, colonia, amenidades planas. Lanza
    SinComparables si hoy no hay suficientes anuncios en la zona."""
    ciudad = sujeto.get("ciudad") or ciudad_mas_cercana(sujeto["lat"], sujeto["lon"]) or ""
    estado = ESTADOS.get(ciudad, "")
    anuncios = await _leer_anuncios(sujeto, ciudad, estado)
    await _ubicar(anuncios, ciudad, estado)
    tabla = _a_tabla(anuncios, ciudad)
    leidos = len(anuncios)
    if tabla.empty:
        raise SinComparables(leidos)

    ciudades_cfg = [c for c in S.ciudades() if c["nombre"] == ciudad]
    limpio = clean.limpiar(tabla, ciudades_cfg or None)
    ok = limpio[limpio["calidad"] == "ok"]
    if ok.empty:
        raise SinComparables(leidos)
    agrupado = dedupe.agrupar(ok)
    base = agrupado[agrupado["es_principal"]].copy()
    ctx = _contexto()
    base = ctx.asignar(base)
    hoy = pd.Timestamp(date.today())
    indice = IndicePrecios()
    base = preparar(base, indice, hoy)
    base = base[np.isfinite(base["y"])].reset_index(drop=True)

    s = dict(sujeto, ciudad=ciudad, municipio=ciudad, zona_indice=ciudad, id=0, cluster_id=0,
             fecha_alta=hoy, ultimo_visto=hoy, dias_publicado=0.0)
    sdf = preparar(ctx.asignar(pd.DataFrame([s])), indice, hoy)
    fila = sdf.iloc[0].to_dict()

    res_a = MotorA(base).estimar(fila)
    res_c = MotorC(base).estimar(fila)
    if not res_a.ok and not res_c.ok:
        raise SinComparables(leidos)

    # σ de cada motor para ESTE caso: A = dispersión de sus comparables ya
    # homologados (con un piso); C = valor fijo sin calibrar.
    sigma_a = max(res_a.dispersion or 0.0, SIGMA_A_MINIMO) if res_a.ok else S.SIGMA_DEFAULT["A"]
    sigmas = {"A": sigma_a, "B": S.SIGMA_DEFAULT["B"], "C": SIGMA_C_SIN_CALIBRAR}
    valores = {"A": res_a.valor if res_a.ok else None, "B": None, "C": res_c.valor if res_c.ok else None}
    seg = S.segmento(valores["A"] or valores["C"])
    delta, n_delta = await _delta(ciudad, seg)
    delta = min(S.DELTA_MAX, delta + delta_extra_por_dias(res_a.comparables if res_a.ok else []))
    ens = ensamblar(valores, sigmas, None, float(fila["m2_base"]), 0.0, delta, n_delta, valores["C"])
    adv = list(ens.advertencias)
    adv.append(f"Modo en vivo: calculado con {len(base)} anuncios reales leídos hoy; "
               "el rango aún no está calibrado con cierres.")

    motores = {
        "A": {"nombre": "Comparables homologados", "ok": res_a.ok, "valor": res_a.valor, "motivo": res_a.motivo,
              "dispersion": res_a.dispersion, "radio_m": res_a.radio_m, "sigma": sigmas["A"]},
        "B": {"nombre": "Modelo estadístico", "ok": False, "valor": None,
              "motivo": "Se activa cuando el modelo se entrene con datos reales.", "sigma": sigmas["B"]},
        "C": {"nombre": "Enfoque físico", "ok": res_c.ok, "valor": res_c.valor, "motivo": res_c.motivo,
              "detalle": res_c.detalle, "sigma": sigmas["C"]},
    }
    for k, p in ens.pesos.items():
        motores[k]["peso"] = round(p, 4)
    asyncio.create_task(_guardar(anuncios, ciudad, estado))
    return {
        "emitido": ens.emitido, "valor": ens.valor, "rango": ens.rango, "confianza": ens.confianza,
        "ancho_relativo": ens.ancho_relativo, "delta": ens.delta, "delta_n": ens.delta_n, "segmento": seg,
        "ciudad": ciudad, "motores": motores, "comparables": res_a.comparables if res_a.ok else [],
        "explicacion": _explicacion(res_a, res_c, sujeto.get("colonia")), "advertencias": adv,
        "version": "v2-en-vivo", "datos": "en_vivo", "anuncios_leidos": leidos,
        "_valor_calc": ens.valor_calculado, "_escala": ens.escala,
    }


async def _delta(ciudad: str, segmento: str) -> tuple[float, int]:
    """Descuento de negociación desde los cierres capturados (si hay)."""
    try:
        from .etl.repo import leer_todo
        filas = await leer_todo("avm_closings", {"select": "municipio,precio_oferta_inicial,precio_cierre"})
        c = pd.DataFrame(filas)
        if c.empty:
            return S.DELTA0, 0
        for col in ("precio_oferta_inicial", "precio_cierre"):
            c[col] = pd.to_numeric(c[col], errors="coerce")
        return TablaDelta.desde_cierres(c).delta(ciudad, segmento)
    except Exception as exc:
        log.info("Sin cierres para δ: %s", exc)
        return S.DELTA0, 0


async def _guardar(anuncios: list[dict], ciudad: str, estado: str) -> None:
    """Lo leído hoy queda en avm_listings para el modelo entrenado."""
    try:
        from .etl.ingest_listings import _a_fila
        from .etl.repo import upsert_listings
        ahora = datetime.now(timezone.utc)
        cfg = {"nombre": ciudad, "estado": estado}
        filas = [_a_fila(a, cfg, ahora) for a in anuncios if a.get("tipo") and a.get("precio")]
        if not filas:
            return
        # fecha_alta no se manda: la base la pone al insertar y no la toca al
        # actualizar (un anuncio conocido conserva su fecha de alta).
        claves = set().union(*(f.keys() for f in filas))
        filas = [{k: f.get(k) for k in claves} for f in filas]   # PostgREST pide las mismas llaves
        await upsert_listings(filas)
    except Exception as exc:     # guardar nunca debe tumbar la valuación
        log.warning("No se guardaron los anuncios en vivo: %s", exc)
