import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from avm import jobs, registry


def test_pipeline_de_punta_a_punta(modelo_chico):
    modelo, extra = modelo_chico
    assert extra["info"]["duplicados"]["clusters_con_duplicados"] > 0      # dedupe trabajó
    assert extra["info"]["limpieza"]["descartes"]                           # limpieza trabajó
    oof = extra["oof"]
    assert {"ln_A", "ln_B", "ln_C", "q10", "q90"} <= set(oof.columns)
    r = modelo.estimar({"tipo": "casa", "lat": 19.70, "lon": -101.19, "m2_construidos": 160, "m2_terreno": 180,
                        "recamaras": 3, "banos": 2, "edad_anios": 10, "conservacion": 4})
    assert r["datos"] == "sinteticos"
    assert set(r["motores"]) == {"A", "B", "C"}
    calculados = [k for k, m in r["motores"].items() if m["ok"]]
    assert abs(sum(r["motores"][k].get("peso", 0) for k in calculados) - 1) < 1e-3   # pesos redondeados a 4 dígitos
    if r["emitido"]:
        assert r["rango"][0] < r["valor"] < r["rango"][1]
    assert 1 <= len(r["explicacion"]) <= 5


def test_sin_fuga_en_validacion(modelo_chico):
    """Si la validación filtrara el propio registro, el error OOF sería ~0."""
    _, extra = modelo_chico
    e = (extra["oof"]["ln_B"] - extra["oof"]["y"]).abs().median()
    assert e > 0.03


def test_guardar_y_cargar(tmp_path, monkeypatch, modelo_chico):
    modelo, _ = modelo_chico
    monkeypatch.setattr(registry, "_dir", lambda: tmp_path)
    registry.guardar_local(modelo, {"mdape": 9.0})
    registry.apuntar_local(modelo.version, {"mdape": 9.0})
    m2, met = registry.cargar_local()
    assert m2.version == modelo.version and met["mdape"] == 9.0
    s = {"tipo": "depto", "lat": 19.71, "lon": -101.18, "m2_construidos": 90, "recamaras": 2, "banos": 2,
         "edad_anios": 5, "conservacion": 4}
    assert m2.estimar(s)["motores"]["B"]["valor"] == pytest.approx(modelo.estimar(s)["motores"]["B"]["valor"])


def test_promocion():
    assert registry.decidir_promocion({"mdape": 10}, None, 2)[0]
    assert registry.decidir_promocion({"mdape": 11.9}, {"mdape": 10}, 2)[0]
    assert not registry.decidir_promocion({"mdape": 12.5}, {"mdape": 10}, 2)[0]


def test_calendario_de_jobs():
    tz = jobs.TZ_MX
    lunes_4 = datetime(2026, 11, 23, 4, 30, tzinfo=tz)
    assert jobs.toca("diario", lunes_4, {}) and jobs.toca("semanal", lunes_4, {})
    assert not jobs.toca("diario", lunes_4, {"diario": "2026-11-23"})
    assert not jobs.toca("mensual", lunes_4, {})
    assert jobs.toca("mensual", datetime(2026, 12, 1, 6, tzinfo=tz), {})
    assert not jobs.toca("diario", datetime(2026, 11, 23, 2, tzinfo=tz), {})


@pytest.fixture()
def cliente(modelo_chico, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.avm_v2 as api
    from avm.service import servicio

    modelo, _ = modelo_chico
    servicio.reemplazar(modelo, {"mdape": 8.0})

    async def usuario(request, **kw):
        if request.headers.get("authorization") != "Bearer ok":
            from fastapi import HTTPException
            raise HTTPException(401, "Sesión requerida.")
        return "00000000-0000-0000-0000-000000000001"

    async def nada(*a, **k):
        return None

    monkeypatch.setattr(api, "require_user_id", usuario)
    monkeypatch.setattr("avm.etl.repo.guardar_prediccion", nada)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def test_api_estimar(cliente):
    cuerpo = {"lat": 19.70, "lon": -101.19, "tipo": "casa", "m2_construidos": 160, "m2_terreno": 180,
              "recamaras": 3, "banos": 2, "edad_anios": 10, "conservacion": 4,
              "amenidades": {"jardin": True, "cajones": 2}}
    assert cliente.post("/avm/v2/estimar", json=cuerpo).status_code == 401
    t = time.perf_counter()
    r = cliente.post("/avm/v2/estimar", json=cuerpo, headers={"Authorization": "Bearer ok"})
    dt = time.perf_counter() - t
    assert r.status_code == 200, r.text
    d = r.json()
    assert dt < 3.0
    assert d["tipo_documento"] == "Opinión Comercial de Valor"
    assert d["confianza"] in ("Alta", "Media", "Baja", "Sin valor")
    assert set(d["motores"]) == {"A", "B", "C"}
    for c in d["comparables"]:
        assert c["url"].startswith("https://")
        assert set(c) == {"url", "precio", "m2", "precio_m2", "distancia_m", "peso", "factor_homologacion"}
    texto = r.text.lower()
    for prohibido in ("firecrawl", "groq", "lightgbm", "apify", "avalúo"):
        assert prohibido not in texto


def test_api_validaciones(cliente):
    h = {"Authorization": "Bearer ok"}
    assert cliente.post("/avm/v2/estimar", json={"tipo": "casa", "m2_construidos": 100}, headers=h).status_code == 422
    assert cliente.post("/avm/v2/estimar", json={"tipo": "terreno", "lat": 19.7, "lon": -101.2},
                        headers=h).status_code == 422


def test_api_estado(cliente):
    d = cliente.get("/avm/v2/estado").json()
    assert d["estado"] == "listo" and d["datos"] == "sinteticos" and "activo" in d
