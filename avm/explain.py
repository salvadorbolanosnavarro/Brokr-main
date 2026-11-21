"""Traduce las contribuciones SHAP del Motor B a 4-5 frases en español.

Las contribuciones están en escala ln(precio). Para explicar el precio por m2,
al grupo "superficie" se le resta el efecto mecánico de ln(m2) (más metros =
más precio total, no más precio por m2). Cada efecto se expresa como % frente
al inmueble típico del modelo de la ciudad.
"""
from __future__ import annotations

import math

from .features import GRUPOS_EXPLICACION

FRASES = {
    "ubicacion": ("La ubicación{donde}", "sube", "baja"),
    "superficie": ("El tamaño del inmueble", "sube", "baja"),
    "antiguedad": ("La antigüedad y el estado de conservación", "suben", "bajan"),
    "distribucion": ("La distribución (recámaras, baños, cajones)", "sube", "baja"),
    "amenidades": ("Las amenidades y el régimen", "suben", "bajan"),
    "mercado": ("El momento de mercado", "sube", "baja"),
}


def frases(contrib: dict, ln_m2: float, ln_m2_tipico: float, colonia: str | None = None,
           maximo: int = 5, umbral: float = 0.01) -> list[str]:
    grupos = {}
    for g, cols in GRUPOS_EXPLICACION.items():
        grupos[g] = sum(float(contrib.get(c, 0.0)) for c in cols)
    # Quitar el efecto mecánico de los m2 sobre el precio total.
    grupos["superficie"] -= (ln_m2 - ln_m2_tipico)
    orden = sorted(grupos.items(), key=lambda kv: abs(kv[1]), reverse=True)
    out = []
    for g, v in orden[:maximo]:
        pct = (math.exp(v) - 1) * 100
        if abs(pct) < umbral * 100:
            continue
        sujeto, sube, baja = FRASES[g]
        sujeto = sujeto.format(donde=f" en {colonia}" if colonia else "")
        verbo = sube if pct > 0 else baja
        out.append(f"{sujeto} {verbo} el precio por m² alrededor de {abs(pct):.0f} % frente al inmueble típico de la ciudad.")
    if not out:
        out.append("El inmueble está muy cerca del precio por m² típico de su zona.")
    return out
