import numpy as np
import pytest

from avm.eval.metrics import cumple, metricas


def test_metricas_valores_conocidos():
    m = metricas([110, 90, 100, 120], [100, 100, 100, 100], bajo=[95, 95, 101, 95], alto=[105, 105, 105, 125])
    assert m["mdape"] == pytest.approx(10.0)
    assert m["pe10"] == pytest.approx(75.0)
    assert m["pe20"] == pytest.approx(100.0)
    assert m["sesgo"] == pytest.approx(1.05)
    assert m["cod"] == pytest.approx(100 * 0.1 / 1.05, abs=0.01)
    assert m["prd"] == pytest.approx(1.0)
    assert m["cobertura"] == pytest.approx(75.0)
    assert m["hit_rate"] == pytest.approx(100.0)


def test_prd_regresivo():
    # Sobrevalúa lo barato y subvalúa lo caro → PRD > 1
    m = metricas([120, 900], [100, 1000])
    assert m["prd"] > 1.03


def test_hit_rate_y_no_emitidos():
    m = metricas([100, None, 110, 100], [100, 100, 100, 100], emitido=[True, False, True, False])
    assert m["hit_rate"] == pytest.approx(50.0) and m["n_emitidos"] == 2


def test_sin_datos():
    m = metricas([np.nan], [100])
    assert m["mdape"] is None and m["n_emitidos"] == 0


def test_cumple_metas():
    ok = cumple({"mdape": 10, "pe10": 50, "pe20": 80, "sesgo": 1.0, "cod": 10, "prd": 1.0, "cobertura": 80})
    assert all(ok.values())
    mal = cumple({"mdape": 20, "pe10": 30, "pe20": 60, "sesgo": 1.1, "cod": 20, "prd": 1.1, "cobertura": 60})
    assert not any(mal.values())
    assert cumple({})["mdape"] is None
