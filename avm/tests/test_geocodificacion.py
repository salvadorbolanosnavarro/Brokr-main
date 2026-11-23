import asyncio

import pytest

from avm import service


class _Resp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


def _cliente(respuestas):
    class C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return _Resp(respuestas["geocode" if "geocode" in url else "places"])
    return C


@pytest.fixture(autouse=True)
def _llave(monkeypatch):
    class S:
        google_places_key = "x"
    monkeypatch.setattr(service, "settings", S())


def test_si_geocoding_esta_deshabilitado_usa_places(monkeypatch):
    monkeypatch.setattr(service.httpx, "AsyncClient", _cliente({
        "geocode": {"status": "REQUEST_DENIED"},
        "places": {"status": "OK", "candidates": [{"types": ["sublocality", "political"],
                                                   "geometry": {"location": {"lat": 19.69, "lng": -101.17}}}]}}))
    assert asyncio.run(service.geocodificar("Chapultepec Norte, Morelia")) == (19.69, -101.17, "aproximada")


def test_direccion_exacta(monkeypatch):
    monkeypatch.setattr(service.httpx, "AsyncClient", _cliente({
        "geocode": {"status": "OK", "results": [{"types": ["street_address"],
                                                 "geometry": {"location": {"lat": 19.7, "lng": -101.2},
                                                              "location_type": "ROOFTOP"}}]},
        "places": {"status": "ZERO_RESULTS"}}))
    assert asyncio.run(service.geocodificar("Av. Camelinas 1500, Morelia"))[2] == "exacta"


def test_solo_la_ciudad_se_rechaza(monkeypatch):
    ciudad = {"types": ["locality", "political"], "geometry": {"location": {"lat": 19.7, "lng": -101.19}}}
    monkeypatch.setattr(service.httpx, "AsyncClient", _cliente({
        "geocode": {"status": "OK", "results": [ciudad]}, "places": {"status": "OK", "candidates": [ciudad]}}))
    with pytest.raises(service.UbicacionAmplia):
        asyncio.run(service.geocodificar("morelia"))


def test_nada_encontrado(monkeypatch):
    monkeypatch.setattr(service.httpx, "AsyncClient", _cliente({
        "geocode": {"status": "ZERO_RESULTS"}, "places": {"status": "ZERO_RESULTS"}}))
    assert asyncio.run(service.geocodificar("zzzz")) is None
