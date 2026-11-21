import math

import pandas as pd
import pytest

from avm import settings as S
from avm.engines.motor_c_fisico import (MotorC, calidad_desde_nse, coef_heidecke, depreciacion_ross_heidecke)
from avm.features import preparar
from avm.indice import IndicePrecios
from .conftest import LAT0, LON0, desplazar, listing


def test_ross_heidecke_valor_conocido():
    # E/VU = 0.5 → D_R = 0.5·(0.5 + 0.25) = 0.375; conservación 3 → C = 0.081
    d = depreciacion_ross_heidecke(30, 60, coef_heidecke(3))
    assert d == pytest.approx(0.375 + (1 - 0.375) * 0.081)


def test_ross_heidecke_extremos():
    assert depreciacion_ross_heidecke(0, 60, 0.0) == 0.0
    assert depreciacion_ross_heidecke(60, 60, 0.0) == pytest.approx(1.0)
    assert depreciacion_ross_heidecke(200, 60, 0.0) == pytest.approx(1.0)   # nunca > 100 %
    assert depreciacion_ross_heidecke(None, 60, 0.0) == 0.0


def test_heidecke_monotono_en_conservacion():
    cs = [coef_heidecke(c) for c in (5, 4, 3, 2, 1)]
    assert cs == sorted(cs)


def _ref(precio_m2_terreno=5000.0, n=5):
    filas = []
    for i in range(n):
        la, lo = desplazar(LAT0, LON0, 20 * i, 0)
        filas.append(listing(i, la, lo, tipo="terreno", precio=precio_m2_terreno * 200, m2t=200.0))
    return preparar(pd.DataFrame(filas), IndicePrecios(), "2026-10-01")


def test_valor_fisico_exacto():
    ref = _ref(5000.0)
    sujeto = listing(99, tipo="casa", m2c=150.0, m2t=200.0, edad_anios=30, conservacion=3,
                     calidad_construccion="media")
    r = MotorC(ref).estimar(sujeto)
    assert r.ok
    vrn = S.tabla("costos_reposicion")["casa"]["media"]
    vu = S.tabla("vida_util")["casa"]["media"]
    d = depreciacion_ross_heidecke(30, vu, coef_heidecke(3))
    assert r.valor == pytest.approx(200 * 5000 + 150 * vrn * (1 - d))
    assert r.detalle["origen_suelo"] == "terrenos H3-8"


def test_suelo_respaldo_h3_7():
    ref = _ref(5000.0)
    ref["h3_8"] = "otro"            # sin terrenos en el H3-8 del sujeto
    r = MotorC(ref).estimar(listing(99, m2t=100.0, calidad_construccion="media"))
    assert r.ok and r.detalle["origen_suelo"] == "terrenos H3-7"


def test_sin_terreno_se_excluye():
    r = MotorC(_ref()).estimar(listing(99, tipo="depto", m2t=None))
    assert not r.ok and "terreno" in r.motivo


def test_sin_terrenos_en_zona_se_excluye():
    ref = _ref()
    ref["h3_8"], ref["h3_7"] = "x", "y"
    assert not MotorC(ref).estimar(listing(99)).ok


def test_mediana_robusta_ignora_outlier():
    ref = _ref(5000.0, n=6)
    ref.loc[0, "precio_aj"] = 5000 * 200 * 50       # captura con ceros de más
    r = MotorC(ref).estimar(listing(99, tipo="terreno", m2t=100.0))
    assert r.valor == pytest.approx(100 * 5000)


def test_calidad_desde_nse():
    assert calidad_desde_nse(1.5) == "economica"
    assert calidad_desde_nse(4.0) == "media"
    assert calidad_desde_nse(6.5) == "residencial_plus"
    assert calidad_desde_nse(None) == "media"
    assert not math.isnan(coef_heidecke(None))
