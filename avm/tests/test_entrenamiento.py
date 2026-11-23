import asyncio

import pandas as pd
import pytest

from avm import entrenamiento as E
from avm import pipeline as P
from avm import registry, synthetic


def _datos(mercado, con_capturados=True):
    lst = mercado.listings.copy()
    c = mercado.closings.copy()
    if con_capturados:
        # Cierres capturados a mano: sin anuncio ligado, con ubicación y m².
        info = lst.set_index("id").loc[c["listing_id"], ["lat", "lon", "m2_construidos", "m2_terreno",
                                                           "recamaras", "banos", "edad_anios", "conservacion"]]
        c = pd.concat([c.reset_index(drop=True), info.reset_index(drop=True)], axis=1)
        c["listing_id"] = None
    return {"listings": lst, "closings": c, "indice": mercado.indice, "contexto": {"ageb": None, "poi": None}}


@pytest.fixture()
def entorno(mercado, monkeypatch, tmp_path):
    from avm.etl import repo
    from avm.service import servicio
    datos = _datos(mercado)

    async def cargar():
        return datos
    monkeypatch.setattr(repo, "cargar_todo", cargar)
    original = P.entrenar
    monkeypatch.setattr(P, "entrenar", lambda *a, **k: original(*a[:6], rounds=60) if len(a) >= 6
                        else original(*a, **{**k, "rounds": 60}))
    monkeypatch.setattr(registry, "_dir", lambda: tmp_path)

    async def nada(*a, **k):
        return False
    monkeypatch.setattr(registry, "subir", nada)
    monkeypatch.setattr(registry, "promover_remoto", nada)
    E._cache_resumen.clear()
    E.estado.clear()
    servicio.modelo, servicio.metricas = None, {}
    return datos


def test_resumen_cuenta_por_ciudad(entorno):
    r = asyncio.run(E.resumen_datos(usar_cache=False))
    assert r["anuncios_utiles"] > 300
    assert set(r["ciudades"]) >= {"Morelia", "Guadalajara"}
    assert r["cierres"] == len(entorno["closings"])


def test_insuficiente_no_entrena(entorno, monkeypatch):
    monkeypatch.setattr(E, "MIN_ANUNCIOS", 10**6)
    r = asyncio.run(E.entrenar_con_datos_reales())
    assert not r["ok"] and r["estado"] == "insuficiente"


def test_entrena_mide_con_cierres_y_promueve(entorno):
    from avm.service import servicio
    r = asyncio.run(E.entrenar_con_datos_reales())
    assert r["ok"] and r["estado"] == "listo" and r["promovido"]
    met = r["metricas"]
    assert "cierres capturados" in met["fuente_medicion"]
    assert met["mdape"] is not None and met["mdape"] < 30
    assert "rango_calibrado_con" in met
    assert servicio.modelo.datos == "reales"
    assert registry.cargar_local()[0].version == r["version"]


def test_cierres_capturados_no_se_ven_a_si_mismos(modelo_chico, mercado):
    modelo, _ = modelo_chico
    d = _datos(mercado)["closings"]
    t = E.evaluar_cierres_capturados(modelo, d.head(15))
    assert len(t) == 15 and t["ens_valor_calc"].notna().all() and (t["ens_escala"] > 0).all()
    assert modelo.delta is not None   # δ original restaurado
