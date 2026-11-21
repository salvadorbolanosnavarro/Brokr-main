import numpy as np
import pandas as pd
import pytest

from avm.engines.motor_b_gbm import MotorB
from avm.features import FEATURES, Featurizer, bloques_espaciales, preparar
from avm.indice import IndicePrecios
from .conftest import LAT0, LON0, desplazar, listing


def test_monotonia_m2_y_edad(modelo_chico):
    modelo, _ = modelo_chico
    fila = modelo.referencia[modelo.referencia["tipo"] == "casa"].iloc[[0]].copy()
    mb = modelo.motor_b
    # Más m² nunca baja el valor total
    valores = []
    for m2 in np.linspace(60, 600, 25):
        f = fila.copy()
        f["ln_m2"] = np.log(m2)
        valores.append(mb.modelo.predict(f[FEATURES].astype(float))[0])
    assert all(b >= a - 1e-9 for a, b in zip(valores, valores[1:]))
    # Más edad (misma conservación) nunca sube el precio por m²
    pm2 = []
    for e in range(0, 70, 3):
        f = fila.copy()
        f["edad_anios"] = e
        pm2.append(mb.predecir_ln_pm2(f)[0])
    assert all(b <= a + 1e-9 for a, b in zip(pm2, pm2[1:]))


def test_cuantiles_ordenados(modelo_chico):
    modelo, _ = modelo_chico
    q = modelo.motor_b.predecir_cuantiles(modelo.referencia.head(200))
    assert np.all(q[0.1] <= q[0.5]) and np.all(q[0.5] <= q[0.9])


def test_shap_suma_a_la_prediccion(modelo_chico):
    modelo, _ = modelo_chico
    f = modelo.referencia.head(5)
    c = modelo.motor_b.contribuciones(f)
    np.testing.assert_allclose(c.sum(axis=1).to_numpy(), modelo.motor_b.modelo.predict(f[FEATURES].astype(float)),
                               atol=1e-6)


def test_recupera_senal_conocida():
    """Precio/m2 = 20 000 · (1.5 si está al norte) · ruido chico: el GBM debe
    recuperar la prima del norte."""
    rng = np.random.default_rng(0)
    filas = []
    for i in range(1200):
        dy = rng.uniform(-3000, 3000)
        la, lo = desplazar(LAT0, LON0, rng.uniform(-3000, 3000), dy)
        pm2 = 20_000 * (1.5 if dy > 0 else 1.0) * np.exp(rng.normal(0, 0.03))
        m2 = rng.uniform(80, 250)
        filas.append(listing(i, la, lo, precio=pm2 * m2, m2c=m2, edad_anios=rng.uniform(0, 30)))
    df = preparar(pd.DataFrame(filas), IndicePrecios(), "2026-10-01")
    fz = Featurizer()
    tr = fz.fit_transform(df)
    mb = MotorB(rounds=150).entrenar(tr, cuantiles=False)
    norte = fz.transform(preparar(pd.DataFrame([listing(-1, *desplazar(LAT0, LON0, 0, 1500))]), IndicePrecios(), "2026-10-01"))
    sur = fz.transform(preparar(pd.DataFrame([listing(-2, *desplazar(LAT0, LON0, 0, -1500))]), IndicePrecios(), "2026-10-01"))
    ratio = np.exp(mb.predecir_ln_pm2(norte)[0] - mb.predecir_ln_pm2(sur)[0])
    assert ratio == pytest.approx(1.5, rel=0.08)


def _df_basico(n=40):
    filas = [listing(i, *desplazar(LAT0, LON0, 15 * i, 0), precio=3e6 + 1e4 * i) for i in range(n)]
    return preparar(pd.DataFrame(filas), IndicePrecios(), "2026-10-01")


def test_knn_excluye_propio_y_duplicados():
    df = _df_basico(30)
    df["cluster_id"] = df["id"]
    # El vecino inmediato del registro 0 es su duplicado con precio absurdo.
    df.loc[1, "cluster_id"] = df.loc[0, "id"]
    df.loc[1, "y"] = df.loc[0, "y"] + 5
    fz = Featurizer(k=5).fit(df)
    sin = fz._knn(df.iloc[[0]].reset_index(drop=True))[0]
    assert sin < 1.0          # si incluyera al duplicado, la mediana saltaría


def test_te_fuera_de_fold_sin_el_propio_registro():
    df = _df_basico(30)
    # Una celda H3-9 con un solo registro: su encoding de entrenamiento debe ser
    # el prior (0), porque el único dato de esa celda es él mismo.
    df.loc[0, ["lat", "lon"]] = desplazar(LAT0, LON0, 8000, 8000)
    for r in (7, 8, 9):
        df[f"h3_{r}"] = [__import__("avm.geo", fromlist=["celda"]).celda(a, b, r) for a, b in zip(df.lat, df.lon)]
    df.loc[0, "y"] += 3
    tr = Featurizer().fit_transform(df)
    assert tr.loc[0, "te_h3_9"] == pytest.approx(0.0)


def test_bloques_espaciales_no_parten_un_bloque():
    df = _df_basico(40)
    folds = bloques_espaciales(df, 5, res=6)
    import avm.geo as g
    bloques = [g.celda(a, b, 6) for a, b in zip(df.lat, df.lon)]
    por_bloque = pd.DataFrame({"b": bloques, "f": folds}).groupby("b")["f"].nunique()
    assert (por_bloque == 1).all()
