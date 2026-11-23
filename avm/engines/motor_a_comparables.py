"""Motor A: comparables homologados (determinista).

1. Candidatos del mismo tipo, en venta, principales (no duplicados), con radio
   creciente 500 m → 1 km → 2 km hasta tener al menos 6.
2. Distancia combinada = geográfica + diferencias normalizadas de superficie,
   recámaras, edad y NSE de la AGEB. Se toman k = 8..15 más cercanos.
3. Homologación por comparable: superficie, edad, conservación, ubicación y
   frente/esquina, cada factor acotado a [0.80, 1.20] y el producto a [0.70, 1.30].
4. Promedio ponderado (en log) con w_i ∝ 1/d_i². Dispersión = desviación
   ponderada del log homologado.

Reemplaza la parte de cálculo del flujo de /api/avm-websearch (que la hacía el
LLM) con la misma idea pericial, pero en Python y sobre avm_listings.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import geo
from .. import settings as S
from .motor_c_fisico import coef_heidecke, depreciacion_ross_heidecke


@dataclass
class ResultadoA:
    ok: bool
    valor: float | None = None
    ln_pm2: float | None = None
    dispersion: float | None = None
    comparables: list[dict] = field(default_factory=list)
    radio_m: int | None = None
    motivo: str = ""


def _acota(x: float, lo: float = S.A_FACTOR_MIN, hi: float = S.A_FACTOR_MAX) -> float:
    return float(min(hi, max(lo, x)))


def _f(v, default=np.nan) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return x if np.isfinite(x) else default


class MotorA:
    def __init__(self, referencia: pd.DataFrame):
        """referencia: listings limpios y principales con precio_aj, m2_base, y,
        lat, lon, tipo, h3_8, edad_anios, conservacion, recamaras, nse_score,
        esquina, dias_publicado, url."""
        ref = referencia[np.isfinite(referencia["y"]) & referencia["lat"].notna()].copy()
        self.ref = ref.reset_index(drop=True)
        # Índice de ubicación por H3-8: mediana del log precio/m2 por tipo.
        self.loc_h3_8 = self.ref.groupby(["tipo", "h3_8"])["y"].median().to_dict()
        self.loc_tipo = self.ref.groupby("tipo")["y"].median().to_dict()

    def _loc(self, tipo: str, h3_8) -> float:
        return self.loc_h3_8.get((tipo, h3_8), self.loc_tipo.get(tipo, np.nan))

    def _depr(self, edad, cons, tipo: str) -> float:
        if tipo == "terreno":
            return 0.0
        vida = S.tabla("vida_util").get(tipo if tipo in ("depto", "local") else "casa", {}).get("media", 60)
        return depreciacion_ross_heidecke(_f(edad, 10.0), vida, coef_heidecke(_f(cons, 3.0)))

    def estimar(self, sujeto: dict, excluir_ids=(), excluir_clusters=()) -> ResultadoA:
        tipo = sujeto["tipo"]
        lat, lon = _f(sujeto.get("lat")), _f(sujeto.get("lon"))
        m2 = _f(sujeto.get("m2_base"))
        if not np.isfinite(lat) or not np.isfinite(m2) or m2 <= 0:
            return ResultadoA(False, motivo="faltan ubicación o superficie")
        cand = self.ref[self.ref["tipo"] == tipo]
        if len(excluir_ids):
            cand = cand[~cand["id"].isin(excluir_ids)]
        if len(excluir_clusters) and "cluster_id" in cand:
            cand = cand[~cand["cluster_id"].isin(excluir_clusters)]
        if cand.empty:
            return ResultadoA(False, motivo="sin comparables del mismo tipo")
        dist = geo.haversine_m(lat, lon, cand["lat"].to_numpy(), cand["lon"].to_numpy())
        radio = None
        for r in S.A_RADIOS_M:
            if (dist <= r).sum() >= S.A_MIN_COMPARABLES:
                radio = r
                break
        if radio is None:
            return ResultadoA(False, motivo=f"menos de {S.A_MIN_COMPARABLES} comparables a 2 km")
        sel = dist <= radio
        c = cand[sel].copy()
        c["dist_m"] = dist[sel]

        e = S.A_ESCALA
        d = c["dist_m"] / e["geo_m"]
        d = d + np.abs(np.log(c["m2_base"].astype(float)) - np.log(m2)) / e["ln_m2"]
        for col, esc in (("recamaras", e["recamaras"]), ("edad_anios", e["edad"]), ("nse_score", e["nse"])):
            v_s = _f(sujeto.get(col))
            if np.isfinite(v_s) and col in c:
                d = d + (np.abs(pd.to_numeric(c[col], errors="coerce") - v_s) / esc).fillna(0.5)
        c["d"] = np.maximum(d.to_numpy(dtype=float), 0.05)
        c = c.nsmallest(S.A_K_MAX, "d")
        if len(c) < S.A_K_MIN and len(c) < S.A_MIN_COMPARABLES:
            return ResultadoA(False, motivo="comparables insuficientes")

        dep_s = self._depr(sujeto.get("edad_anios"), sujeto.get("conservacion"), tipo)
        loc_s = self._loc(tipo, sujeto.get("h3_8"))
        esq_s = _f(sujeto.get("esquina"), 0.0)
        filas = []
        for _, r in c.iterrows():
            f_sup = _acota((r["m2_base"] / m2) ** S.A_ELASTICIDAD_SUP)
            dep_c = self._depr(r.get("edad_anios"), 3.0, tipo)
            dep_c_cons = self._depr(r.get("edad_anios"), r.get("conservacion"), tipo)
            dep_s_edad = self._depr(sujeto.get("edad_anios"), 3.0, tipo)
            f_edad = _acota((1 - dep_s_edad) / max(1 - dep_c, 0.05))
            # Efecto de la conservación aislado del de la edad (ratio de ratios).
            cons_s = max(1 - dep_s, 0.05) / max(1 - dep_s_edad, 0.05)
            cons_c = max(1 - dep_c_cons, 0.05) / max(1 - dep_c, 0.05)
            f_cons = _acota(cons_s / cons_c)
            loc_c = self._loc(tipo, r.get("h3_8"))
            f_ubic = _acota(float(np.exp(loc_s - loc_c))) if np.isfinite(loc_s) and np.isfinite(loc_c) else 1.0
            esq_c = _f(r.get("esquina"), 0.0)
            f_esq = _acota(S.A_ESQUINA ** (esq_s - esq_c))
            prod = float(np.clip(f_sup * f_edad * f_cons * f_ubic * f_esq, S.A_PRODUCTO_MIN, S.A_PRODUCTO_MAX))
            filas.append({
                "id": int(r["id"]) if "id" in r else None, "url": r.get("url"),
                "precio": float(r["precio"]), "m2": float(r["m2_base"]),
                "precio_m2": float(r["precio_aj"] / r["m2_base"]),
                "dist_m": round(float(r["dist_m"])), "d": float(r["d"]),
                "factores": {"superficie": round(f_sup, 3), "edad": round(f_edad, 3), "conservacion": round(f_cons, 3),
                             "ubicacion": round(f_ubic, 3), "esquina": round(f_esq, 3)},
                "factor_total": round(prod, 3),
                "ln_pm2_hom": float(r["y"] + np.log(prod)),
                "dias_publicado": _f(r.get("dias_publicado"), 0.0),
            })
        w = np.array([1.0 / f["d"] ** 2 for f in filas])
        w = w / w.sum()
        ln = np.array([f["ln_pm2_hom"] for f in filas])
        media = float(np.sum(w * ln))
        disp = float(np.sqrt(np.sum(w * (ln - media) ** 2)))
        for f, wi in zip(filas, w):
            f["peso"] = round(float(wi), 4)
        return ResultadoA(True, float(np.exp(media) * m2), media, disp, filas, radio)
