"""Limpieza de anuncios antes de entrenar o usar como comparables.

Reglas (cada descarte deja su motivo):
- operación distinta de venta, o precio de renta disfrazado de venta;
- preventa mezclada con inmuebles terminados;
- superficies imposibles;
- coordenada fuera de la ciudad (bbox del municipio) → descartado;
  coordenada = centroide de colonia → precision_ubicacion = 'aproximada';
- precio/m2 a más de 3 MAD de la mediana de su H3-8 (con respaldo H3-7).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .. import geo
from .. import settings as S
from ..features import m2_base

PRECIO_MIN_VENTA = {"casa": 250_000, "depto": 250_000, "terreno": 50_000, "local": 150_000}
M2_RANGO = {"casa": (25, 3000), "depto": (20, 1500), "local": (8, 5000), "terreno": (40, 200_000)}
PM2_RANGO = {"casa": (2_000, 200_000), "depto": (4_000, 250_000), "local": (2_000, 300_000), "terreno": (80, 80_000)}
RE_PREVENTA = re.compile(r"\bpre[\s-]?venta\b|\bentrega en\b|\ben construcci[oó]n\b", re.I)
RE_RENTA = re.compile(r"\b(renta|arriendo|alquiler)\b", re.I)
MAD_K = 3.0


def _motivo(df: pd.DataFrame, mask: pd.Series, motivo: str) -> None:
    nuevo = mask & (df["calidad"] != "descartado")
    df.loc[nuevo, "calidad"] = "descartado"
    df.loc[nuevo, "motivo_descarte"] = motivo


def limpiar(df: pd.DataFrame, ciudades: list[dict] | None = None, mezclar_preventa: bool = False) -> pd.DataFrame:
    out = df.copy()
    out["calidad"] = "ok"
    out["motivo_descarte"] = None
    desc = out["descripcion"].fillna("").astype(str) if "descripcion" in out else pd.Series("", index=out.index)

    _motivo(out, out["operacion"] != "venta", "no es venta")
    if "moneda" in out:
        _motivo(out, out["moneda"].fillna("MXN").str.upper() != "MXN", "precio en otra moneda")
    minimo = out["tipo"].map(PRECIO_MIN_VENTA).fillna(150_000)
    _motivo(out, out["precio"] < minimo, "precio de renta o error de captura")
    _motivo(out, desc.str.contains(RE_RENTA) & (out["precio"] < minimo * 4) & ~desc.str.contains("venta", case=False),
            "anuncio de renta publicado como venta")
    if not mezclar_preventa:
        _motivo(out, desc.str.contains(RE_PREVENTA), "preventa (no se mezcla con terminados)")

    base = pd.Series(m2_base(out), index=out.index).astype(float)
    lo = out["tipo"].map(lambda t: M2_RANGO.get(t, (10, 1e6))[0])
    hi = out["tipo"].map(lambda t: M2_RANGO.get(t, (10, 1e6))[1])
    _motivo(out, base.isna() | (base < lo) | (base > hi), "superficie imposible o faltante")
    if "m2_terreno" in out and "m2_construidos" in out:
        # Casa con más construcción que 4 veces el terreno: casi siempre captura.
        _motivo(out, (out["tipo"] == "casa") & (out["m2_construidos"] > 4 * out["m2_terreno"]),
                "construcción incompatible con el terreno")

    pm2 = out["precio"] / base
    lo = out["tipo"].map(lambda t: PM2_RANGO.get(t, (1, 1e7))[0])
    hi = out["tipo"].map(lambda t: PM2_RANGO.get(t, (1, 1e7))[1])
    _motivo(out, (pm2 < lo) | (pm2 > hi), "precio por m2 imposible")

    # ── geovalidación ──
    _motivo(out, out["lat"].isna() | out["lon"].isna(), "sin coordenadas")
    if ciudades:
        bbox = {c["nombre"]: c["bbox"] for c in ciudades}
        col = "ciudad" if "ciudad" in out else "municipio"
        fuera = [not (c in bbox and geo.dentro_bbox(la, lo_, bbox[c])) if pd.notna(la) else False
                 for c, la, lo_ in zip(out[col], out["lat"], out["lon"])]
        _motivo(out, pd.Series(fuera, index=out.index), "coordenada fuera de la ciudad")
    if "precision_ubicacion" not in out:
        out["precision_ubicacion"] = "exacta"
    # Muchas filas con exactamente la misma coordenada = centroide de colonia.
    coord = out["lat"].round(5).astype(str) + "," + out["lon"].round(5).astype(str)
    repetidas = coord.map(coord.value_counts()) >= 4
    out.loc[repetidas, "precision_ubicacion"] = "aproximada"

    # ── outliers robustos por zona ──
    ok = out["calidad"] == "ok"
    lpm2 = np.log(pm2.where(pm2 > 0))
    out["_lpm2"] = lpm2
    marcado = pd.Series(False, index=out.index)
    for tipo in out["tipo"].unique():
        sel = ok & (out["tipo"] == tipo)
        for col in ("h3_8", "h3_7"):
            grupos = out[sel].groupby(col)["_lpm2"]
            med = grupos.transform("median")
            mad = grupos.transform(lambda s: np.median(np.abs(s - np.median(s))) * 1.4826)
            n = grupos.transform("count")
            usable = (n >= 8) & (mad > 0)
            z = (out.loc[sel, "_lpm2"] - med).abs() / mad
            fuera = usable & (z > MAD_K)
            marcado.loc[fuera[fuera].index] = True
            sel = sel & ~marcado
    _motivo(out, marcado, "precio por m2 atípico para su zona (> 3 MAD)")
    return out.drop(columns=["_lpm2"])


def resumen(df: pd.DataFrame) -> dict:
    return {"total": int(len(df)), "ok": int((df["calidad"] == "ok").sum()),
            "descartes": df.loc[df["calidad"] == "descartado", "motivo_descarte"].value_counts().to_dict()}
