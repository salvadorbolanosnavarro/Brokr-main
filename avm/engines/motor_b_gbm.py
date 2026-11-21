"""Motor B: LightGBM sobre el log del precio por m2.

Detalle técnico importante: se entrena sobre z = y + ln(m2) = ln(precio).
Como ln(m2) es un dato del inmueble, el residuo z - ẑ es idéntico a y - ŷ, así
que la pérdida Huber es exactamente la misma que entrenar sobre y. La ventaja es
que en z sí se puede imponer la restricción del encargo "más m2 no baja el valor
total" como restricción monótona creciente sobre ln(m2). La edad va con
restricción decreciente (a igual conservación, más edad no sube el precio/m2).

Además del modelo Huber (estimado central) se entrenan cuantiles q10/q50/q90.
LightGBM no admite restricciones monótonas en el objetivo cuantílico, así que
solo el estimado central las lleva; los cuantiles dan la forma del rango.
"""
from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

from .. import settings as S
from ..features import FEATURES, matriz

MONOTONAS = {"ln_m2": 1, "ln_m2_terreno": 1, "edad_anios": -1}


def _monotone_vector() -> list[int]:
    return [MONOTONAS.get(f, 0) for f in FEATURES]


@dataclass
class ResultadoB:
    ok: bool
    ln_pm2: float | None = None
    valor: float | None = None
    q: dict | None = None            # {0.1: ln_pm2, 0.5: ..., 0.9: ...}
    contribuciones: dict | None = None
    motivo: str = ""


class MotorB:
    def __init__(self, rounds: int = S.B_ROUNDS, params: dict | None = None):
        self.rounds = rounds
        self.params = dict(S.B_PARAMS, **(params or {}))
        self.modelo: lgb.Booster | None = None
        self.cuantiles: dict[float, lgb.Booster] = {}

    def _params(self, objetivo: str, alpha: float | None = None) -> dict:
        p = dict(self.params)
        p["objective"] = objetivo
        if objetivo != "quantile":
            # LightGBM no permite restricciones monótonas con objetivo
            # cuantílico: el valor central (Huber) las respeta; los cuantiles
            # solo dan la forma del rango.
            p["monotone_constraints"] = _monotone_vector()
            p["monotone_constraints_method"] = "advanced"
        if objetivo == "huber":
            p["alpha"] = S.B_HUBER_ALPHA
        if objetivo == "quantile":
            p["alpha"] = alpha
        return p

    def entrenar(self, df: pd.DataFrame, cuantiles: bool = True) -> "MotorB":
        df = df[np.isfinite(df["y"]) & np.isfinite(df["ln_m2"])]
        X = matriz(df)
        z = (df["y"] + df["ln_m2"]).to_numpy()
        ds = lgb.Dataset(X, z, free_raw_data=False, params={"verbose": -1})
        self.modelo = lgb.train(self._params("huber"), ds, num_boost_round=self.rounds)
        self.cuantiles = {}
        if cuantiles:
            for q in S.B_QUANTILES:
                self.cuantiles[q] = lgb.train(self._params("quantile", q), ds, num_boost_round=self.rounds)
        return self

    def predecir_ln_pm2(self, df: pd.DataFrame) -> np.ndarray:
        X = matriz(df)
        return self.modelo.predict(X) - df["ln_m2"].to_numpy()

    def predecir_cuantiles(self, df: pd.DataFrame) -> dict[float, np.ndarray]:
        X = matriz(df)
        ln_m2 = df["ln_m2"].to_numpy()
        crudo = {q: m.predict(X) - ln_m2 for q, m in self.cuantiles.items()}
        if not crudo:
            return {}
        # Los cuantiles se entrenan por separado y pueden cruzarse: se ordenan.
        qs = sorted(crudo)
        apilado = np.sort(np.vstack([crudo[q] for q in qs]), axis=0)
        return {q: apilado[i] for i, q in enumerate(qs)}

    def contribuciones(self, df: pd.DataFrame) -> pd.DataFrame:
        """SHAP exacto de árboles (TreeSHAP) que LightGBM calcula nativo.
        Columnas = FEATURES + 'base'. Están en escala z (ln precio)."""
        X = matriz(df)
        c = self.modelo.predict(X, pred_contrib=True)
        return pd.DataFrame(c, columns=FEATURES + ["base"], index=df.index)

    def estimar(self, sujeto_df: pd.DataFrame) -> ResultadoB:
        if self.modelo is None:
            return ResultadoB(False, motivo="modelo no entrenado")
        ln = float(self.predecir_ln_pm2(sujeto_df)[0])
        qs = {q: float(v[0]) for q, v in self.predecir_cuantiles(sujeto_df).items()}
        m2 = float(np.exp(sujeto_df["ln_m2"].iloc[0]))
        contrib = self.contribuciones(sujeto_df).iloc[0].to_dict()
        return ResultadoB(True, ln, float(np.exp(ln) * m2), qs, contrib)
