import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.filterwarnings("ignore")

from avm import geo  # noqa: E402

LAT0, LON0 = 19.7027, -101.1923


def listing(i, lat=LAT0, lon=LON0, tipo="casa", precio=3_000_000.0, m2c=150.0, m2t=160.0, **kw):
    base = {
        "id": i, "url": f"https://x.mx/{i}", "fuente": "inmuebles24", "tipo": tipo, "operacion": "venta",
        "precio": precio, "moneda": "MXN", "m2_construidos": m2c if tipo != "terreno" else np.nan,
        "m2_terreno": m2t, "recamaras": 3.0, "banos": 2.0, "edad_anios": 10.0, "conservacion": 4.0,
        "lat": lat, "lon": lon, "ciudad": "Morelia", "municipio": "Morelia", "zona_indice": "Morelia",
        "fecha_alta": pd.Timestamp("2026-09-01"), "ultimo_visto": pd.Timestamp("2026-10-01"),
        "nse_score": 4.0, "esquina": 0.0,
    }
    base.update(kw)
    for r in (7, 8, 9):
        base[f"h3_{r}"] = geo.celda(base["lat"], base["lon"], r)
    return base


def desplazar(lat, lon, dx_m, dy_m):
    return lat + dy_m / 111_320.0, lon + dx_m / (111_320.0 * np.cos(np.radians(lat)))


@pytest.fixture(scope="session")
def mercado():
    from avm import synthetic
    return synthetic.generar(n_por_ciudad=500, semilla=3, n_cierres_por_ciudad=60)


@pytest.fixture(scope="session")
def modelo_chico(mercado):
    from avm import pipeline, synthetic
    modelo, extra = pipeline.entrenar(mercado.listings, mercado.closings, mercado.indice, synthetic.FECHA_FIN,
                                      datos="sinteticos", rounds=80)
    return modelo, extra
