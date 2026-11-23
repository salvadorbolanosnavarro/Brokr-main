"""Índice de precios por zona y trimestre (avm_index) para llevar cada precio
observado a la fecha de valuación: P_t0 = P_ti * I_t0 / I_ti."""
from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


def trimestre(fecha) -> str:
    f = pd.Timestamp(fecha)
    return f"{f.year}T{(f.month - 1) // 3 + 1}"


def _orden(t: str) -> int:
    anio, q = t.split("T")
    return int(anio) * 4 + int(q) - 1


class IndicePrecios:
    """Serie por zona; si falta un trimestre usa el más cercano anterior (o
    posterior si no hay anterior). Sin datos de la zona → factor 1."""

    def __init__(self, filas: Iterable[Mapping] = ()):
        self._series: dict[str, list[tuple[int, float]]] = {}
        for f in filas:
            zona = str(f["zona"]).strip().lower()
            self._series.setdefault(zona, []).append((_orden(str(f["trimestre"])), float(f["valor"])))
        for zona in self._series:
            self._series[zona].sort()

    def valor(self, zona: str, fecha) -> float | None:
        serie = self._series.get(str(zona or "").strip().lower())
        if not serie:
            return None
        objetivo = _orden(trimestre(fecha))
        anteriores = [v for t, v in serie if t <= objetivo]
        return anteriores[-1] if anteriores else serie[0][1]

    def factor(self, zona: str, fecha_obs, fecha_valuacion) -> float:
        i_obs = self.valor(zona, fecha_obs)
        i_val = self.valor(zona, fecha_valuacion)
        if not i_obs or not i_val:
            return 1.0
        return i_val / i_obs

    def factores(self, zonas, fechas_obs, fecha_valuacion) -> np.ndarray:
        cache: dict[tuple[str, str], float] = {}
        out = np.ones(len(zonas))
        for i, (z, f) in enumerate(zip(zonas, fechas_obs)):
            clave = (str(z), trimestre(f))
            if clave not in cache:
                cache[clave] = self.factor(z, f, fecha_valuacion)
            out[i] = cache[clave]
        return out

    def to_rows(self) -> list[dict]:
        rows = []
        for zona, serie in self._series.items():
            for t, v in serie:
                rows.append({"zona": zona, "trimestre": f"{t // 4}T{t % 4 + 1}", "valor": v})
        return rows


def hoy() -> date:
    return date.today()
