"""Contexto urbano para las ciudades activas (avm/config/ciudades.json).

Fuentes públicas (descarga directa):
- INEGI Censo 2020, AGEB urbana (ageb_mza_urbana_XX_cpv2020_csv.zip):
  población, viviendas, escolaridad, % viviendas con auto, internet, computadora.
- INEGI DENUE (denue_XX_csv.zip): conteos de escuelas, hospitales/clínicas,
  supermercados, bancos y restaurantes por H3-9. Del DENUE solo se leen código
  de actividad, AGEB y coordenadas (nunca nombres, teléfonos ni correos). El
  centroide de cada AGEB = promedio de sus negocios: así se ubica la AGEB sin
  descargar polígonos.
- OpenStreetMap (Overpass): distancia a avenida principal y a parque.
- NSE: estimado por AGEB con una regla tipo AMAI sobre variables del Censo
  (escolaridad, auto, internet, computadora). AMAI no publica NSE por AGEB; el
  campo se llama nse_amai pero la fuente queda como "estimado Censo 2020".
- Rezago CONEVAL por AGEB: opcional; si ciudades.json trae 'coneval_csv'.

Uso:  python -m avm.etl.load_context [--ciudad Morelia] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import io
import logging
import zipfile

import httpx
import numpy as np
import pandas as pd

from .. import geo
from .. import settings as S

log = logging.getLogger("broquer.avm_v2.contexto")
URL_CENSO = "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/ageb_manzana/ageb_mza_urbana_{ent}_cpv2020_csv.zip"
URL_DENUE = "https://www.inegi.org.mx/contenidos/masiva/denue/denue_{ent}_csv.zip"
URL_OVERPASS = "https://overpass-api.de/api/interpreter"

# Prefijos SCIAN 2023 → categoría
SCIAN = {
    "escuelas": ("6111",),
    "hospitales": ("622", "6211", "6212", "6213", "6214"),
    "supermercados": ("462111", "462112"),
    "bancos": ("5221",),
    "restaurantes": ("7225",),
}
# Distribución nacional urbana aproximada de NSE (AMAI 2022), de mayor a menor.
NSE_NIVELES = [("A/B", 7, 0.06), ("C+", 6, 0.13), ("C", 5, 0.17), ("C-", 4, 0.17), ("D+", 3, 0.18),
               ("D", 2, 0.21), ("E", 1, 0.08)]


async def _bajar(url: str, timeout: float = 600) -> bytes:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


def _csv_de_zip(contenido: bytes, patron: str, **kw) -> pd.DataFrame:
    z = zipfile.ZipFile(io.BytesIO(contenido))
    # El CSV más grande de la carpeta: algunos estados traen además una
    # bitácora de cambios en la misma carpeta.
    candidatos = [i for i in z.infolist() if patron in i.filename and i.filename.endswith(".csv")]
    nombre = max(candidatos, key=lambda i: i.file_size).filename
    try:
        with z.open(nombre) as f:
            return pd.read_csv(f, **kw)
    except UnicodeDecodeError:
        # INEGI publica algunos estados en UTF-8 y otros en latin-1.
        kw["encoding"] = "latin-1"
        with z.open(nombre) as f:
            return pd.read_csv(f, **kw)


def censo_ageb(df: pd.DataFrame, cve_mun: list[str]) -> pd.DataFrame:
    """Filas 'Total AGEB urbana' → variables por AGEB."""
    df = df.rename(columns=lambda c: c.strip().lstrip("﻿"))
    df = df[(df["NOM_LOC"] == "Total AGEB urbana") & (df["MUN"].astype(str).str.zfill(3).isin(cve_mun))].copy()
    num = lambda c: pd.to_numeric(df[c].replace({"*": np.nan, "N/D": np.nan}), errors="coerce")
    # Denominador de las variables VPH_*: total de viviendas particulares
    # habitadas (TVIVPARHAB), no VIVPAR_HAB.
    viv = num("TVIVPARHAB").replace(0, np.nan)
    out = pd.DataFrame({
        "cvegeo": df["ENTIDAD"].astype(str).str.zfill(2) + df["MUN"].astype(str).str.zfill(3)
                  + df["LOC"].astype(str).str.zfill(4) + df["AGEB"].astype(str).str.zfill(4),
        "municipio_cve": df["MUN"].astype(str).str.zfill(3),
        "poblacion": num("POBTOT"), "viviendas": num("VIVPAR_HAB"),
        "escolaridad_prom": num("GRAPROES").replace(0, np.nan),
        "pct_auto": (100 * num("VPH_AUTOM") / viv).clip(0, 100),
        "pct_internet": (100 * num("VPH_INTER") / viv).clip(0, 100),
        "pct_computadora": (100 * num("VPH_PC") / viv).clip(0, 100),
    })
    return out.reset_index(drop=True)


def nse_estimado(ctx: pd.DataFrame) -> pd.DataFrame:
    """Índice compuesto (z-scores) → percentil → nivel según la distribución
    AMAI. Ordinal nse_score: 7 = A/B … 1 = E."""
    out = ctx.copy()
    cols = ["escolaridad_prom", "pct_auto", "pct_internet", "pct_computadora"]
    z = sum((out[c] - out[c].mean()) / (out[c].std(ddof=0) or 1) for c in cols) / len(cols)
    pct = z.rank(pct=True, ascending=False)        # 0 = más alto
    limites = np.cumsum([p for _, _, p in NSE_NIVELES])
    nivel = np.searchsorted(limites, pct.fillna(1.0).to_numpy(), side="left").clip(0, len(NSE_NIVELES) - 1)
    out["nse_amai"] = [NSE_NIVELES[i][0] for i in nivel]
    out["nse_score"] = [float(NSE_NIVELES[i][1]) for i in nivel]
    out.loc[z.isna(), ["nse_amai", "nse_score"]] = [None, np.nan]
    return out


def denue_resumen(df: pd.DataFrame, cve_mun: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """→ (centroides por AGEB, conteos por H3-9)."""
    df = df[df["cve_mun"].astype(str).str.zfill(3).isin(cve_mun)].copy()
    df["latitud"] = pd.to_numeric(df["latitud"], errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")
    df = df.dropna(subset=["latitud", "longitud"])
    df["cvegeo"] = (df["cve_ent"].astype(str).str.zfill(2) + df["cve_mun"].astype(str).str.zfill(3)
                    + df["cve_loc"].astype(str).str.zfill(4) + df["ageb"].astype(str).str.zfill(4))
    centroides = df.groupby("cvegeo").agg(lat=("latitud", "mean"), lon=("longitud", "mean")).reset_index()
    df["h3_9"] = geo.celdas(df["latitud"], df["longitud"], 9)
    act = df["codigo_act"].astype(str)
    conteos = pd.DataFrame({"h3_9": df["h3_9"]})
    for cat, prefijos in SCIAN.items():
        conteos[cat] = act.str.startswith(prefijos).astype(int)
    conteos = conteos.groupby("h3_9").sum().reset_index()
    return centroides, conteos


def densidad(ctx: pd.DataFrame, centroides: pd.DataFrame) -> pd.Series:
    """Densidad aproximada: población / área de la celda H3-8 de su centroide
    (sin polígonos no hay área exacta de la AGEB)."""
    area_km2 = 0.7373  # área promedio de un hexágono H3-8
    m = ctx.merge(centroides, on="cvegeo", how="left")
    return (m["poblacion"] / area_km2).round(1)


def _overpass_query(bbox) -> str:
    s, w, n, e = bbox
    return f"""[out:json][timeout:120];
(way["highway"~"^(primary|trunk|motorway|secondary)$"]({s},{w},{n},{e});
 way["leisure"="park"]({s},{w},{n},{e}););
out geom;"""


def distancias_osm(elementos: list[dict], celdas_h3: list[str]) -> pd.DataFrame:
    from shapely import STRtree
    from shapely.geometry import LineString, Point
    import h3

    avenidas, parques = [], []
    for el in elementos:
        pts = [(p["lon"], p["lat"]) for p in el.get("geometry", [])]
        if len(pts) < 2:
            continue
        linea = LineString(pts)
        (parques if el.get("tags", {}).get("leisure") == "park" else avenidas).append(linea)
    filas = []
    arboles = {k: STRtree(v) if v else None for k, v in (("av", avenidas), ("pq", parques))}
    for c in celdas_h3:
        la, lo = h3.cell_to_latlng(c)
        p = Point(lo, la)
        fila = {"h3_9": c}
        for k, col, geoms in (("av", "dist_avenida_m", avenidas), ("pq", "dist_parque_m", parques)):
            t = arboles[k]
            if t is None:
                fila[col] = None
                continue
            g = geoms[int(t.nearest(p))]
            q = g.interpolate(g.project(p))
            fila[col] = round(float(geo.haversine_m(la, lo, q.y, q.x)), 1)
        filas.append(fila)
    return pd.DataFrame(filas)


async def cargar_ciudad(ciudad: dict, dry_run: bool = False) -> dict:
    ent, muns = ciudad["cve_ent"], ciudad["cve_mun"]
    censo = _csv_de_zip(await _bajar(URL_CENSO.format(ent=ent)), "conjunto_de_datos", dtype=str)
    ctx = nse_estimado(censo_ageb(censo, muns))
    denue = _csv_de_zip(await _bajar(URL_DENUE.format(ent=ent)), "conjunto_de_datos", encoding="latin-1",
                        dtype=str, usecols=["codigo_act", "cve_ent", "cve_mun", "cve_loc", "ageb", "latitud", "longitud"])
    centroides, conteos = denue_resumen(denue, muns)
    ctx["densidad_hab_km2"] = densidad(ctx, centroides)
    ctx = ctx.merge(centroides, on="cvegeo", how="left")
    ctx["estado"], ctx["municipio"] = ciudad["estado"], ciudad["nombre"]
    ctx["rezago_coneval"] = None
    ctx["fuente"] = "INEGI Censo 2020 + DENUE (centroide) · NSE estimado"
    # Distancias OSM para las celdas H3-9 con negocios (las urbanizadas).
    poi = conteos.copy()
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(URL_OVERPASS, data={"data": _overpass_query(ciudad["bbox"])})
            r.raise_for_status()
        dist = distancias_osm(r.json().get("elements", []), poi["h3_9"].tolist())
        poi = poi.merge(dist, on="h3_9", how="left")
    except Exception as exc:
        log.warning("OSM no disponible para %s: %s", ciudad["nombre"], exc)
        poi["dist_avenida_m"] = None
        poi["dist_parque_m"] = None
    import h3
    centro = ciudad["centro"]
    poi["dist_centro_m"] = [round(float(geo.haversine_m(*h3.cell_to_latlng(c), *centro)), 1) for c in poi["h3_9"]]
    poi["fuente"] = "DENUE + OSM"
    res = {"ciudad": ciudad["nombre"], "agebs": int(len(ctx)), "agebs_con_centroide": int(ctx["lat"].notna().sum()),
           "celdas_h3_9": int(len(poi))}
    if not dry_run:
        from .repo import registros
        from core.database import upsert_rows
        cols_ctx = ["cvegeo", "estado", "municipio", "poblacion", "viviendas", "densidad_hab_km2", "escolaridad_prom",
                    "pct_auto", "pct_internet", "pct_computadora", "nse_amai", "nse_score", "rezago_coneval",
                    "lat", "lon", "fuente"]
        filas = registros(ctx, cols_ctx)
        for i in range(0, len(filas), 500):
            await upsert_rows("avm_context_ageb", filas[i:i + 500], conflict="cvegeo", prefer="return=minimal")
        cols_poi = ["h3_9", "escuelas", "hospitales", "supermercados", "bancos", "restaurantes",
                    "dist_avenida_m", "dist_parque_m", "dist_centro_m", "fuente"]
        filas = registros(poi, cols_poi)
        for i in range(0, len(filas), 500):
            await upsert_rows("avm_poi_counts", filas[i:i + 500], conflict="h3_9", prefer="return=minimal")
    return res


async def correr(nombre: str | None = None, dry_run: bool = False) -> list[dict]:
    out = []
    for c in S.ciudades():
        if nombre and c["nombre"].lower() != nombre.lower():
            continue
        out.append(await cargar_ciudad(c, dry_run))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ciudad")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(asyncio.run(correr(a.ciudad, a.dry_run)))
