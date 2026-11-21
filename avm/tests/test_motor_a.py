import numpy as np
import pandas as pd
import pytest

from avm import settings as S
from avm.engines.motor_a_comparables import MotorA
from avm.features import preparar
from avm.indice import IndicePrecios
from .conftest import LAT0, LON0, desplazar, listing


def _prep(filas):
    return preparar(pd.DataFrame(filas), IndicePrecios(), "2026-10-01")


def _anillo(n, radio_m, pm2=20_000.0, inicio=0, **kw):
    precio = kw.pop("precio", pm2 * 150)
    filas = []
    for i in range(n):
        ang = 2 * np.pi * i / n
        la, lo = desplazar(LAT0, LON0, radio_m * np.cos(ang), radio_m * np.sin(ang))
        filas.append(listing(inicio + i, la, lo, precio=precio, m2c=150.0, **kw))
    return filas


def test_comparables_identicos_dan_el_precio_exacto():
    ref = _prep(_anillo(12, 200))
    sujeto = _prep([listing(999)]).iloc[0].to_dict()
    r = MotorA(ref).estimar(sujeto)
    assert r.ok
    assert r.valor == pytest.approx(20_000 * 150, rel=1e-9)
    assert r.dispersion == pytest.approx(0.0, abs=1e-9)
    assert r.radio_m == 500
    assert S.A_K_MIN <= len(r.comparables) <= S.A_K_MAX


def test_radio_crece_hasta_tener_seis():
    ref = _prep(_anillo(4, 300) + _anillo(4, 1500, inicio=10))
    r = MotorA(ref).estimar(_prep([listing(999)]).iloc[0].to_dict())
    assert r.ok and r.radio_m == 2000


def test_menos_de_seis_a_2km_no_calcula():
    ref = _prep(_anillo(5, 300) + _anillo(10, 3000, inicio=10))
    r = MotorA(ref).estimar(_prep([listing(999)]).iloc[0].to_dict())
    assert not r.ok


def test_factores_acotados():
    # Comparables 10 veces más grandes: el factor de superficie no pasa de 1.20
    filas = [dict(f, m2_construidos=1500.0, precio=1500 * 20_000.0) for f in _anillo(8, 200)]
    ref = _prep(filas)
    r = MotorA(ref).estimar(_prep([listing(999, m2c=150.0)]).iloc[0].to_dict())
    for c in r.comparables:
        for v in c["factores"].values():
            assert S.A_FACTOR_MIN <= v <= S.A_FACTOR_MAX
        assert S.A_PRODUCTO_MIN <= c["factor_total"] <= S.A_PRODUCTO_MAX
    assert all(c["factores"]["superficie"] == pytest.approx(1.20) for c in r.comparables)


def test_pesos_inverso_distancia_al_cuadrado():
    ref = _prep(_anillo(6, 100) + _anillo(6, 400, inicio=10, precio=30_000 * 150))
    r = MotorA(ref).estimar(_prep([listing(999)]).iloc[0].to_dict())
    w = np.array([c["peso"] for c in r.comparables])
    d = np.array([c["d"] for c in r.comparables])
    esperado = (1 / d ** 2) / np.sum(1 / d ** 2)
    np.testing.assert_allclose(w, esperado, atol=1e-4)
    # Los cercanos (más baratos) pesan más: el valor queda más cerca de 20 mil/m²
    assert r.valor / 150 < 25_000


def test_excluye_propio_y_cluster():
    filas = _anillo(10, 200)
    ref = _prep(filas)
    ref["cluster_id"] = ref["id"]
    sujeto = ref.iloc[0].to_dict()
    r = MotorA(ref).estimar(sujeto, excluir_ids=(sujeto["id"],), excluir_clusters=(sujeto["id"],))
    assert sujeto["id"] not in [c["id"] for c in r.comparables]


def test_solo_mismo_tipo():
    ref = _prep(_anillo(10, 200, tipo="depto"))
    assert not MotorA(ref).estimar(_prep([listing(999)]).iloc[0].to_dict()).ok
