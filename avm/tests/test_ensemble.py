import math

import numpy as np
import pandas as pd
import pytest

from avm import settings as S
from avm.ensemble import (ConformalMondrian, TablaDelta, TablaSigma, bajar_nivel, delta_extra_por_dias, ensamblar,
                          nivel_confianza, pesos_inverso_varianza)


def test_pesos_inverso_varianza():
    w = pesos_inverso_varianza({"A": 0.1, "B": 0.2})
    assert w["A"] == pytest.approx(0.8) and w["B"] == pytest.approx(0.2)


def test_motor_ausente_se_excluye_y_renormaliza():
    q = {0.1: math.log(19_000), 0.5: math.log(20_000), 0.9: math.log(21_000)}
    r = ensamblar({"A": 2e6, "B": 3e6, "C": None}, {"A": 0.1, "B": 0.1, "C": 0.1}, q, 100, 0.0, 0.0, 0, None)
    assert set(r.pesos) == {"A", "B"} and sum(r.pesos.values()) == pytest.approx(1.0)
    assert r.valor == pytest.approx(math.sqrt(2e6 * 3e6))   # media geométrica con pesos iguales


def test_formula_ln_v_con_delta():
    q = {0.1: math.log(19_500), 0.5: math.log(20_000), 0.9: math.log(20_500)}
    r = ensamblar({"A": 2e6, "B": 2e6, "C": 2e6}, {"A": 0.1, "B": 0.2, "C": 0.3}, q, 100, 0.0, 0.06, 20, 2e6)
    assert r.valor == pytest.approx(2e6 * (1 - 0.06))


def test_delta_encogimiento_bayesiano():
    c = pd.DataFrame({"municipio": "Morelia", "precio_oferta_inicial": [1e6] * 20, "precio_cierre": [0.9e6] * 20})
    d, n = TablaDelta.desde_cierres(c).delta("Morelia", "social_medio")
    assert n == 20 and d == pytest.approx((20 * 0.10 + 20 * 0.06) / 40)


def test_delta_sin_cierres_es_delta0():
    assert TablaDelta.desde_cierres(pd.DataFrame()).delta("X", "residencial") == (S.DELTA0, 0)


def test_delta_extra_por_dias():
    comps = [{"peso": 0.5, "dias_publicado": 200}, {"peso": 0.5, "dias_publicado": 10}]
    assert delta_extra_por_dias(comps) == pytest.approx(S.DELTA_EXTRA_SOBREPRECIO / 2)


def test_niveles_de_confianza():
    assert nivel_confianza(0.10) == "Alta"
    assert nivel_confianza(0.20) == "Media"
    assert nivel_confianza(0.30) == "Baja"
    assert nivel_confianza(0.45) == "Sin valor"
    assert bajar_nivel("Alta") == "Media" and bajar_nivel("Media") == "Baja" and bajar_nivel("Baja") == "Baja"


def test_mas_de_40_no_emite():
    q = {0.1: math.log(14_000), 0.5: math.log(20_000), 0.9: math.log(28_000)}
    r = ensamblar({"B": 2e6}, {"A": .1, "B": .1, "C": .1}, q, 100, 0.0, 0.0, 0, None)
    assert not r.emitido and r.valor is None and "visita" in " ".join(r.advertencias)


def test_fisico_muy_distinto_baja_un_nivel():
    q = {0.1: math.log(19_000), 0.5: math.log(20_000), 0.9: math.log(21_000)}   # ancho 10 % → Alta
    base = ensamblar({"B": 2e6}, {"A": .1, "B": .1, "C": .1}, q, 100, 0.0, 0.0, 0, None)
    assert base.confianza == "Alta"
    r = ensamblar({"B": 2e6}, {"A": .1, "B": .1, "C": .1}, q, 100, 0.0, 0.0, 0, 3e6)
    assert r.confianza == "Media"


def test_conformal_mondrian_cobertura_80():
    rng = np.random.default_rng(1)
    n = 4000
    ciudad = rng.choice(["A", "B"], n)
    escala = np.where(ciudad == "A", 0.05, 0.20)        # B es mucho más incierta
    y = rng.normal(0, escala)
    q10 = np.full(n, -0.06)
    q90 = np.full(n, 0.06)                               # cuantiles mal calibrados a propósito
    seg = np.array(["s"] * n)
    cal = slice(0, 2000)
    cm = ConformalMondrian().ajustar(y[cal], q10[cal], q90[cal], ciudad[cal], seg[cal])
    for c in ("A", "B"):
        m = (ciudad == c)
        m[:2000] = False
        Q = cm.ajuste(c, "s")
        cobertura = np.mean((y[m] >= q10[m] - Q) & (y[m] <= q90[m] + Q))
        assert 0.76 <= cobertura <= 0.84, (c, cobertura)


def test_conformal_respaldo_global():
    cm = ConformalMondrian(n_min=50).ajustar([0.0] * 30, [-0.1] * 30, [0.1] * 30, ["X"] * 30, ["s"] * 30)
    assert cm.ajuste("X", "s") == cm.ajuste("_global", "_global")
    assert ConformalMondrian.from_dict(cm.to_dict()).q == cm.q


def test_tabla_sigma_respaldos():
    err = pd.DataFrame({"motor": "A", "ciudad": "M", "tipo": "casa", "segmento": "s",
                        "e": np.random.default_rng(0).normal(0, 0.1, 100)})
    t = TablaSigma.desde_errores(err)
    assert t.sigma("A", "M", "casa", "s") == pytest.approx(0.1, rel=0.25)
    assert t.sigma("A", "Otra", "depto", "x") == pytest.approx(t.sigma("A", None, None, None))
    assert t.sigma("C", "M", "casa", "s") == S.SIGMA_DEFAULT["C"]
