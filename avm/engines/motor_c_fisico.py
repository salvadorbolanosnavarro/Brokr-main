"""Motor C: enfoque físico (costo).

    V_C = S_terreno * VU_suelo * F_res + Σ S_c * VRN_c * (1 - D_c)
    D_R = 0.5 * (E/VU + (E/VU)^2)            (Ross)
    D   = D_R + (1 - D_R) * C_cons           (Heidecke)

VU_suelo = mediana robusta del precio/m2 de terrenos ofertados en el mismo
H3-8 (respaldo H3-7). Si no hay terrenos suficientes, residual de casas del
H3-8: (P - construcción depreciada) / S_terreno.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import settings as S


def coef_heidecke(conservacion) -> float:
    tabla = S.tabla("heidecke")
    try:
        c = int(round(float(conservacion)))
    except (TypeError, ValueError):
        c = 3
    return float(tabla[str(min(5, max(1, c)))])


def depreciacion_ross_heidecke(edad, vida_util, c_cons: float) -> float:
    try:
        e = max(0.0, float(edad))
    except (TypeError, ValueError):
        e = 0.0
    if not np.isfinite(e):
        e = 0.0
    r = min(1.0, e / float(vida_util)) if vida_util else 1.0
    d_r = 0.5 * (r + r * r)
    return float(min(1.0, d_r + (1.0 - d_r) * c_cons))


def calidad_desde_nse(nse_score) -> str:
    """NSE ordinal 1..7 → calidad de construcción (si el usuario no la da)."""
    try:
        n = float(nse_score)
    except (TypeError, ValueError):
        return "media"
    if not np.isfinite(n):
        return "media"
    if n < 2.8:
        return "economica"
    if n < 4.8:
        return "media"
    if n < 6.0:
        return "residencial"
    return "residencial_plus"


def _mediana_robusta(x: np.ndarray) -> float | None:
    x = x[np.isfinite(x) & (x > 0)]
    if len(x) == 0:
        return None
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826
    if mad > 0:
        x = x[np.abs(x - med) <= 3 * mad]
    return float(np.median(x))


@dataclass
class ResultadoC:
    ok: bool
    valor: float | None = None
    motivo: str = ""
    detalle: dict = field(default_factory=dict)


class MotorC:
    def __init__(self, referencia: pd.DataFrame):
        """referencia: listings limpios con columnas tipo, precio_aj (precio a
        fecha de valuación), m2_terreno, m2_construidos, edad_anios,
        conservacion, h3_7, h3_8, nse_score."""
        self.ref = referencia

    def valor_suelo(self, h3_8: str | None, h3_7: str | None) -> tuple[float | None, str]:
        terr = self.ref[(self.ref["tipo"] == "terreno") & (self.ref["m2_terreno"] > 0)]
        for col, cel, etiqueta in (("h3_8", h3_8, "terrenos H3-8"), ("h3_7", h3_7, "terrenos H3-7")):
            if not cel:
                continue
            sub = terr[terr[col] == cel]
            if len(sub) >= S.C_MIN_TERRENOS:
                return _mediana_robusta((sub["precio_aj"] / sub["m2_terreno"]).to_numpy()), etiqueta
        # Residual de casas: lo que queda del precio después de la construcción.
        casas = self.ref[(self.ref["tipo"] == "casa") & (self.ref["m2_terreno"] > 0) & (self.ref["m2_construidos"] > 0)]
        vida = S.tabla("vida_util")
        vrn = S.tabla("costos_reposicion")
        for col, cel, etiqueta in (("h3_8", h3_8, "residual casas H3-8"), ("h3_7", h3_7, "residual casas H3-7")):
            if not cel:
                continue
            sub = casas[casas[col] == cel]
            if len(sub) < S.C_MIN_TERRENOS:
                continue
            res = []
            for _, r in sub.iterrows():
                q = calidad_desde_nse(r.get("nse_score"))
                d = depreciacion_ross_heidecke(r.get("edad_anios"), vida["casa"][q], coef_heidecke(r.get("conservacion")))
                construccion = r["m2_construidos"] * vrn["casa"][q] * (1 - d)
                res.append((r["precio_aj"] - construccion) / r["m2_terreno"])
            v = _mediana_robusta(np.array(res, dtype=float))
            if v:
                return v, etiqueta
        return None, "sin terrenos"

    def estimar(self, sujeto: dict) -> ResultadoC:
        tipo = sujeto.get("tipo")
        s_t = float(sujeto.get("m2_terreno") or 0)
        if s_t <= 0:
            return ResultadoC(False, motivo="sin superficie de terreno")
        vu_suelo, origen = self.valor_suelo(sujeto.get("h3_8"), sujeto.get("h3_7"))
        if not vu_suelo:
            return ResultadoC(False, motivo="sin terrenos comparables en la zona")
        f_res = float(sujeto.get("f_res") or 1.0)
        v_terreno = s_t * vu_suelo * f_res
        if tipo == "terreno":
            return ResultadoC(True, v_terreno, detalle={"valor_terreno": v_terreno, "vu_suelo": vu_suelo,
                                                         "origen_suelo": origen, "valor_construccion": 0.0})
        tt = "local" if tipo == "local" else ("depto" if tipo == "depto" else "casa")
        calidad = sujeto.get("calidad_construccion") or calidad_desde_nse(sujeto.get("nse_score"))
        vida = S.tabla("vida_util")[tt][calidad]
        vrn = S.tabla("costos_reposicion")[tt][calidad]
        bloques = sujeto.get("construcciones") or [{
            "m2": sujeto.get("m2_construidos"), "edad": sujeto.get("edad_anios"),
            "conservacion": sujeto.get("conservacion"),
        }]
        v_constr = 0.0
        dets = []
        for b in bloques:
            m2 = float(b.get("m2") or 0)
            if m2 <= 0:
                continue
            d = depreciacion_ross_heidecke(b.get("edad"), vida, coef_heidecke(b.get("conservacion")))
            v = m2 * vrn * (1 - d)
            v_constr += v
            dets.append({"m2": m2, "depreciacion": round(d, 4), "valor": v})
        if v_constr <= 0:
            return ResultadoC(False, motivo="sin superficie construida")
        return ResultadoC(True, v_terreno + v_constr, detalle={
            "valor_terreno": v_terreno, "vu_suelo": vu_suelo, "origen_suelo": origen,
            "valor_construccion": v_constr, "calidad": calidad, "vrn_m2": vrn, "vida_util": vida,
            "bloques": dets,
        })
