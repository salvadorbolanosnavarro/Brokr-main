"""Métricas estándar de valuación masiva (IAAO) y del rango.

ratio = estimado / real
- MdAPE: mediana de |ratio − 1| (en %)
- PE10 / PE20: % de estimados a ±10 % / ±20 % del real
- Sesgo: mediana del ratio (ideal 1.00)
- COD: 100 · promedio(|ratio − mediana|) / mediana (uniformidad)
- PRD: promedio(ratio) / (Σ estimado / Σ real) (regresividad; ideal 0.98–1.03)
- Cobertura: % de reales dentro del rango
- Hit rate: % de solicitudes con valor emitido
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import settings as S


def metricas(estimado, real, bajo=None, alto=None, emitido=None) -> dict:
    est = np.asarray(estimado, float)
    rea = np.asarray(real, float)
    emit = np.ones(len(est), bool) if emitido is None else np.asarray(emitido, bool)
    ok = emit & np.isfinite(est) & np.isfinite(rea) & (rea > 0) & (est > 0)
    out = {"n": int(len(est)), "n_emitidos": int(ok.sum()),
           "hit_rate": round(100 * ok.sum() / len(est), 1) if len(est) else None}
    if ok.sum() == 0:
        return out | {k: None for k in ("mdape", "pe10", "pe20", "sesgo", "cod", "prd", "cobertura")}
    r = est[ok] / rea[ok]
    med = float(np.median(r))
    out.update({
        "mdape": round(100 * float(np.median(np.abs(r - 1))), 2),
        "pe10": round(100 * float(np.mean(np.abs(r - 1) <= 0.10)), 1),
        "pe20": round(100 * float(np.mean(np.abs(r - 1) <= 0.20)), 1),
        "sesgo": round(med, 3),
        "cod": round(100 * float(np.mean(np.abs(r - med))) / med, 2),
        "prd": round(float(np.mean(r)) / (float(est[ok].sum()) / float(rea[ok].sum())), 3),
    })
    if bajo is not None and alto is not None:
        lo = np.asarray(bajo, float)[ok]
        hi = np.asarray(alto, float)[ok]
        out["cobertura"] = round(100 * float(np.mean((rea[ok] >= lo) & (rea[ok] <= hi))), 1)
    else:
        out["cobertura"] = None
    return out


def cumple(m: dict) -> dict:
    """Compara contra las metas de la fase 1. None = no se puede evaluar."""
    M = S.METAS

    def chk(v, f):
        return None if v is None else bool(f(v))

    return {
        "mdape": chk(m.get("mdape"), lambda v: v <= M["mdape_max"]),
        "pe10": chk(m.get("pe10"), lambda v: v >= M["pe10_min"]),
        "pe20": chk(m.get("pe20"), lambda v: v >= M["pe20_min"]),
        "sesgo": chk(m.get("sesgo"), lambda v: M["sesgo"][0] <= v <= M["sesgo"][1]),
        "cod": chk(m.get("cod"), lambda v: v <= M["cod_max"]),
        "prd": chk(m.get("prd"), lambda v: M["prd"][0] <= v <= M["prd"][1]),
        "cobertura": chk(m.get("cobertura"), lambda v: M["cobertura"][0] <= v <= M["cobertura"][1]),
    }


def por_grupo(df: pd.DataFrame, grupos: list[str], est="estimado", real="real", bajo="bajo", alto="alto",
              emitido="emitido") -> pd.DataFrame:
    filas = []
    for clave, g in df.groupby(grupos):
        clave = clave if isinstance(clave, tuple) else (clave,)
        m = metricas(g[est], g[real], g[bajo] if bajo in g else None, g[alto] if alto in g else None,
                     g[emitido] if emitido in g else None)
        filas.append(dict(zip(grupos, clave)) | m)
    return pd.DataFrame(filas)
