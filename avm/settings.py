"""Constantes del AVM v2. Todo lo que es una decisión de modelado vive aquí.

Las variables de entorno se leen solo en core/config.py (regla del repo); este
módulo solo agrega las constantes del modelo y las tablas editables de config/.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent / "config"

TIPOS = ("casa", "depto", "terreno", "local")
CALIDADES = ("economica", "media", "residencial", "residencial_plus")

# ── Motor A: comparables ─────────────────────────────────────────────────────
A_RADIOS_M = (500, 1000, 2000)
A_MIN_COMPARABLES = 6
A_K_MIN = 8
A_K_MAX = 15
A_FACTOR_MIN, A_FACTOR_MAX = 0.80, 1.20
A_PRODUCTO_MIN, A_PRODUCTO_MAX = 0.70, 1.30
# Elasticidad del precio/m2 respecto a la superficie: lotes más grandes valen
# menos por m2. F_sup = (S_comp / S_suj) ** A_ELASTICIDAD_SUP.
A_ELASTICIDAD_SUP = 0.12
A_ESQUINA = 1.05
# Escalas de la distancia combinada (una unidad = "tan distinto como 1 km").
A_ESCALA = {"geo_m": 1000.0, "ln_m2": 0.25, "recamaras": 1.5, "edad": 15.0, "nse": 1.0}
A_DIAS_SOBREPRECIO = 180

# ── Motor B: GBM ─────────────────────────────────────────────────────────────
B_FOLDS = 5
B_TE_SUAVIZADO = 10.0        # m del promedio bayesiano del target encoding
B_KNN_VECINOS = 10
B_QUANTILES = (0.10, 0.50, 0.90)
B_PARAMS = {
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 20,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "verbose": -1,
    "seed": 7,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 2,
}
B_ROUNDS = 600
B_HUBER_ALPHA = 0.15         # en log: ~15 % de error antes de volverse lineal

# ── Motor C: físico ──────────────────────────────────────────────────────────
C_MIN_TERRENOS = 3

# ── Ensamble ─────────────────────────────────────────────────────────────────
DELTA0 = 0.06
KAPPA = 20.0
DELTA_MAX = 0.20
DELTA_EXTRA_SOBREPRECIO = 0.03   # si todos los comparables llevan > 180 días
SEGMENTOS = ((0, 3_000_000, "social_medio"), (3_000_000, 7_000_000, "residencial"),
             (7_000_000, float("inf"), "residencial_plus"))
COBERTURA_OBJETIVO = 0.80
CONFORMAL_MIN_GRUPO = 20
CONFIANZA_CORTES = ((0.15, "Alta"), (0.25, "Media"), (0.40, "Baja"))
C_DIFERENCIA_MAX = 0.30
SIGMA_DEFAULT = {"A": 0.18, "B": 0.15, "C": 0.25}

# ── Validación y promoción ───────────────────────────────────────────────────
HOLDOUT_MESES = 3
# Tres tamaños de bloque espacial, cada uno con su propósito:
# - H3-6 (~36 km²): prueba de estrés "zona sin ningún dato" (lo pidió el encargo).
# - H3-8 (~0.7 km²): calibración de σ por motor y del rango conformal; imita
#   producción (el sujeto tiene vecinos, pero nunca se ve a sí mismo ni a los
#   anuncios de su manzana).
# - H3-10 (~0.015 km²): folds internos del target encoding. Con bloques más
#   grandes que la celda codificada, la celda entera cae en un fold y el
#   encoding de entrenamiento sería siempre el promedio global (y distinto del
#   de producción).
H3_BLOQUE_CV = 6
H3_BLOQUE_CALIBRACION = 8
H3_BLOQUE_TE = 10
PROMOCION_MAX_EMPEORA_PTS = 2.0
METAS = {
    "mdape_max": 12.0, "pe10_min": 45.0, "pe20_min": 75.0,
    "sesgo": (0.97, 1.03), "cod_max": 15.0, "prd": (0.98, 1.03), "cobertura": (76.0, 84.0),
}


def segmento(precio: float) -> str:
    for lo, hi, nombre in SEGMENTOS:
        if lo <= precio < hi:
            return nombre
    return SEGMENTOS[-1][2]


@lru_cache(maxsize=None)
def tabla(nombre: str) -> dict:
    data = json.loads((CONFIG_DIR / f"{nombre}.json").read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def ciudades() -> list[dict]:
    return list(tabla("ciudades")["ciudades"])
