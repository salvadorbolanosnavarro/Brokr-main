import asyncio

import numpy as np
import pytest

from avm import en_vivo
from avm.geo import haversine_m


def _anuncios_cerca(mercado, lat, lon, radio_m=1500, tipos=("casa", "terreno")):
    l = mercado.listings
    l = l[(l["ciudad"] == "Morelia") & l["tipo"].isin(tipos) & ~l["_outlier"] & l["_dup_de"].isna()]
    d = haversine_m(lat, lon, l["lat"].to_numpy(), l["lon"].to_numpy())
    out = []
    for (_, r), dist in zip(l.iterrows(), d):
        if dist > radio_m:
            continue
        out.append({"url": r["url"], "fuente": r["fuente"], "tipo": r["tipo"], "operacion": "venta",
                    "precio": float(r["precio"]), "moneda": "MXN",
                    "m2_construidos": None if r["tipo"] == "terreno" else float(r["m2_construidos"]),
                    "m2_terreno": float(r["m2_terreno"]), "recamaras": r["recamaras"], "banos": r["banos"],
                    "estacionamientos": None, "ubicacion": "Colonia X", "titulo": r["tipo"],
                    "lat": float(r["lat"]), "lon": float(r["lon"]), "precision_ubicacion": "aproximada",
                    "_valor_real": float(r["_valor_real"])})
    return out


@pytest.fixture()
def simulado(monkeypatch):
    estado = {"anuncios": []}

    async def leer(sujeto, ciudad, estado_):
        return [dict(a) for a in estado["anuncios"]]

    async def nada(*a, **k):
        return None

    async def delta(ciudad, seg):
        return 0.06, 0
    monkeypatch.setattr(en_vivo, "_leer_anuncios", leer)
    monkeypatch.setattr(en_vivo, "_ubicar", nada)
    monkeypatch.setattr(en_vivo, "_guardar", nada)
    monkeypatch.setattr(en_vivo, "_delta", delta)
    return estado


def test_valua_con_anuncios_de_hoy(mercado, simulado):
    casas = [a for a in _anuncios_cerca(mercado, 19.70, -101.19) if a["tipo"] == "casa"]
    assert len(casas) >= 6
    simulado["anuncios"] = _anuncios_cerca(mercado, 19.70, -101.19)
    s = {"tipo": "casa", "lat": 19.70, "lon": -101.19, "m2_construidos": 150, "m2_terreno": 160,
         "recamaras": 3, "banos": 2, "edad_anios": 10, "conservacion": 4}
    r = asyncio.run(en_vivo.estimar(s))
    assert r["datos"] == "en_vivo" and r["ciudad"] == "Morelia"
    assert r["motores"]["A"]["ok"] and not r["motores"]["B"]["ok"]
    assert r["anuncios_leidos"] == len(simulado["anuncios"])
    assert any("en vivo" in a for a in r["advertencias"])
    # El valor queda en el orden de magnitud de los comparables (oferta − δ).
    pm2 = np.median([a["precio"] / a["m2_construidos"] for a in casas])
    assert 0.5 < r["_valor_calc"] / (pm2 * 150) < 1.5
    for c in r["comparables"]:
        assert c["url"].startswith("https://")


def test_sin_anuncios_avisa(simulado):
    simulado["anuncios"] = []
    with pytest.raises(en_vivo.SinComparables):
        asyncio.run(en_vivo.estimar({"tipo": "casa", "lat": 19.70, "lon": -101.19, "m2_construidos": 150}))


def test_pocos_comparables_y_sin_terreno_avisa(mercado, simulado):
    simulado["anuncios"] = [a for a in _anuncios_cerca(mercado, 19.70, -101.19) if a["tipo"] == "casa"][:3]
    with pytest.raises(en_vivo.SinComparables):
        asyncio.run(en_vivo.estimar({"tipo": "depto", "lat": 19.70, "lon": -101.19, "m2_construidos": 90}))
