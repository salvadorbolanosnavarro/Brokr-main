"""Asigna variables de contexto (Censo por AGEB, DENUE/OSM por H3-9) a
anuncios y sujetos.

- AGEB: la más cercana por centroide (el centroide se calcula en
  etl/load_context.py como el promedio de los negocios DENUE de esa AGEB, así
  no hace falta descargar polígonos del Marco Geoestadístico).
- POI: unión exacta por H3-9.
- Si no hay tablas de contexto (p. ej. modelo sintético o ciudad recién
  agregada), se imputa con la mediana de los 5 anuncios más cercanos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from . import geo
from . import settings as S
from .features import CONTEXTO

COLS_AGEB = ["nse_score", "escolaridad_prom", "pct_auto", "pct_internet", "pct_computadora",
             "densidad_hab_km2", "rezago_num"]
COLS_POI = ["escuelas", "hospitales", "supermercados", "bancos", "restaurantes",
            "dist_avenida_m", "dist_parque_m", "dist_centro_m"]
MAX_DIST_AGEB_M = 1500


class Contexto:
    def __init__(self, ageb: pd.DataFrame | None = None, poi: pd.DataFrame | None = None,
                 referencia: pd.DataFrame | None = None):
        self.ageb = ageb if ageb is not None and len(ageb) else None
        self.poi = poi.set_index("h3_9") if poi is not None and len(poi) else None
        self._arbol_ageb = None
        if self.ageb is not None:
            a = self.ageb.dropna(subset=["lat", "lon"]).reset_index(drop=True)
            self.ageb = a
            self._arbol_ageb = BallTree(np.radians(a[["lat", "lon"]].to_numpy(float)), metric="haversine")
        self.ref = None
        if referencia is not None and len(referencia):
            cols = ["lat", "lon"] + [c for c in CONTEXTO if c in referencia]
            self.ref = referencia[cols].dropna(subset=["lat", "lon"]).reset_index(drop=True)
            self._arbol_ref = BallTree(np.radians(self.ref[["lat", "lon"]].to_numpy(float)), metric="haversine")

    def asignar(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for c in CONTEXTO:
            if c not in out:
                out[c] = np.nan
        pts = out[["lat", "lon"]].to_numpy(float)
        ok = np.isfinite(pts).all(axis=1)
        if self._arbol_ageb is not None and ok.any():
            d, i = self._arbol_ageb.query(np.radians(pts[ok]), k=1)
            d = d[:, 0] * geo.R_TIERRA_M
            filas = self.ageb.iloc[i[:, 0]].reset_index(drop=True)
            cerca = d <= MAX_DIST_AGEB_M
            idx = np.flatnonzero(ok)[cerca]
            for c in COLS_AGEB:
                if c in filas:
                    vals = filas.loc[cerca, c].to_numpy()
                    out.iloc[idx, out.columns.get_loc(c)] = np.where(
                        out.iloc[idx][c].isna(), vals, out.iloc[idx][c])
            if "ageb_cvegeo" in out:
                out.iloc[idx, out.columns.get_loc("ageb_cvegeo")] = filas.loc[cerca, "cvegeo"].to_numpy()
        if self.poi is not None and "h3_9" in out:
            for c in COLS_POI:
                if c in self.poi:
                    out[c] = out[c].fillna(out["h3_9"].map(self.poi[c]))
        # Distancia al centro histórico desde la configuración de ciudades.
        centros = {c["nombre"]: c["centro"] for c in S.ciudades()}
        if "ciudad" in out:
            dc = [geo.haversine_m(la, lo, *centros[c]) if c in centros and np.isfinite(la) else np.nan
                  for c, la, lo in zip(out["ciudad"], out["lat"], out["lon"])]
            out["dist_centro_m"] = out["dist_centro_m"].fillna(pd.Series(dc, index=out.index))
        # Lo que siga vacío: mediana de los 5 anuncios más cercanos.
        if self.ref is not None and ok.any():
            faltan = [c for c in CONTEXTO if c in self.ref and out[c].isna().any()]
            if faltan:
                _, vec = self._arbol_ref.query(np.radians(pts[ok]), k=min(5, len(self.ref)))
                for c in faltan:
                    med = np.nanmedian(self.ref[c].to_numpy(float)[vec], axis=1)
                    col = out.columns.get_loc(c)
                    actual = out.iloc[np.flatnonzero(ok), col].to_numpy(float)
                    out.iloc[np.flatnonzero(ok), col] = np.where(np.isnan(actual), med, actual)
        return out


def ciudad_mas_cercana(lat: float, lon: float) -> str | None:
    mejor, dmin = None, 60_000.0
    for c in S.ciudades():
        d = float(geo.haversine_m(lat, lon, *c["centro"]))
        if d < dmin:
            mejor, dmin = c["nombre"], d
    return mejor
