"""Genera avm/config/demo_agebs.csv: AGEB urbanas reales de las ciudades
activas (centroide por DENUE, NSE estimado y variables del Censo 2020).

La demo sintética usa este archivo para que la geografía de precios siga la
realidad socioeconómica de cada zona en vez de zonas caras/baratas al azar.

    python -m avm.etl.demo_context --censo-dir <carpeta con censoXX.zip y denueXX.zip>
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .. import settings as S
from . import load_context as L

SALIDA = S.CONFIG_DIR / "demo_agebs.csv"
COLS = ["ciudad", "cvegeo", "lat", "lon", "viviendas", "nse_score", "escolaridad_prom", "pct_auto",
        "pct_internet", "pct_computadora"]


def construir(carpeta: Path) -> pd.DataFrame:
    partes = []
    for c in S.ciudades():
        ent, muns = c["cve_ent"], c["cve_mun"]
        censo = L._csv_de_zip((carpeta / f"censo{ent}.zip").read_bytes(), "conjunto_de_datos", dtype=str)
        ctx = L.nse_estimado(L.censo_ageb(censo, muns))
        denue = L._csv_de_zip((carpeta / f"denue{ent}.zip").read_bytes(), "conjunto_de_datos", encoding="latin-1",
                              dtype=str, usecols=["codigo_act", "cve_ent", "cve_mun", "cve_loc", "ageb", "latitud",
                                                  "longitud"])
        centroides, _ = L.denue_resumen(denue, muns)
        ctx = ctx.merge(centroides, on="cvegeo", how="inner")
        ctx = ctx.dropna(subset=["lat", "lon", "nse_score"])
        ctx = ctx[ctx["viviendas"].fillna(0) >= 20]
        ctx["ciudad"] = c["nombre"]
        partes.append(ctx)
    out = pd.concat(partes, ignore_index=True)[COLS]
    for col in ("lat", "lon"):
        out[col] = out[col].round(5)
    for col in ("escolaridad_prom", "pct_auto", "pct_internet", "pct_computadora"):
        out[col] = out[col].round(1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--censo-dir", required=True)
    a = ap.parse_args()
    df = construir(Path(a.censo_dir))
    df.to_csv(SALIDA, index=False)
    print(df.groupby("ciudad").size().to_dict(), "→", SALIDA)
