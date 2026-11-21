from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from avm.etl import clean, dedupe, extract_text, ingest_listings as ing
from .conftest import LAT0, LON0, desplazar, listing


def test_dedupe_agrupa_y_elige_principal():
    a = listing(1, fecha_alta=pd.Timestamp("2026-05-01"), edad_anios=np.nan)       # menos completo
    b = listing(2, *desplazar(LAT0, LON0, 10, 5), precio=3_050_000, fecha_alta=pd.Timestamp("2026-06-01"))
    c = listing(3, *desplazar(LAT0, LON0, 12, 8), precio=3_040_000, fecha_alta=pd.Timestamp("2026-04-01"))
    lejos = listing(4, *desplazar(LAT0, LON0, 500, 0))
    distinto = listing(5, *desplazar(LAT0, LON0, 5, 0), precio=4_500_000)           # +50 % de precio
    out = dedupe.agrupar(pd.DataFrame([a, b, c, lejos, distinto]))
    cl = out.set_index("id")["cluster_id"]
    assert cl[1] == cl[2] == cl[3] and cl[4] != cl[1] and cl[5] != cl[1]
    principales = out[out["es_principal"]].set_index("id")
    assert 3 in principales.index          # completo y el más antiguo
    assert len(principales) == 3


def test_dedupe_por_hash_de_foto():
    a = listing(1, foto_phash="abcd")
    b = listing(2, *desplazar(LAT0, LON0, 900, 0), precio=2e6, foto_phash="abcd")
    out = dedupe.agrupar(pd.DataFrame([a, b]))
    assert out["cluster_id"].nunique() == 1


def test_limpieza_descarta_lo_imposible():
    filas = [listing(i, *desplazar(LAT0, LON0, 30 * i, 0), precio=3e6 * (1 + 0.01 * i)) for i in range(12)]
    filas.append(listing(100, precio=12_000))                                  # renta disfrazada
    filas.append(listing(101, precio=3e8))                                     # precio/m2 imposible
    filas.append(listing(102, m2c=5.0))                                        # superficie imposible
    filas.append(listing(103, operacion="renta"))
    filas.append(listing(104, descripcion="Preventa, entrega en 2027"))
    filas.append(listing(105, lat=25.0, lon=-100.0))                           # fuera de Morelia
    filas.append(listing(106, moneda="USD"))
    out = clean.limpiar(pd.DataFrame(filas), [{"nombre": "Morelia", "bbox": [19.6, -101.35, 19.8, -101.05]}])
    malos = set(out.loc[out["calidad"] == "descartado", "id"])
    assert {100, 101, 102, 103, 104, 105, 106} <= malos
    assert not (set(range(12)) & malos)


def test_limpieza_outlier_mad_por_zona():
    rng = np.random.default_rng(0)
    filas = [listing(i, *desplazar(LAT0, LON0, rng.uniform(-100, 100), rng.uniform(-100, 100)),
                     precio=3e6 * np.exp(rng.normal(0, 0.05))) for i in range(30)]
    filas.append(listing(99, precio=3e6 * 2.2))
    out = clean.limpiar(pd.DataFrame(filas))
    assert out.set_index("id").loc[99, "motivo_descarte"].startswith("precio por m2 atípico")


TEXTO = """Encabezado
ANUNCIOS ESTRUCTURADOS DE LA PÁGINA (alta confianza, 2 anuncios, cada línea es un anuncio distinto con sus propios datos):
1) Casa en venta en Chapultepec | Chapultepec Oriente, Morelia | precio=3250000 | moneda=MXN | m2_construccion=180 | m2_terreno=160 | recamaras=3 | banos=2.5 | url=https://www.inmuebles24.com/propiedades/casa-123.html?x=1
2) Departamento en renta | Centro | operacion=renta | precio=12000 | url=https://www.vivanuncios.com.mx/a-renta/9

texto libre"""


def test_parsear_bloque_estructurado():
    a = ing.parsear_bloque(TEXTO)
    assert len(a) == 2
    casa, depto = a
    assert casa["tipo"] == "casa" and casa["precio"] == 3_250_000 and casa["m2_construidos"] == 180
    assert casa["url"] == "https://www.inmuebles24.com/propiedades/casa-123.html"
    assert casa["fuente"] == "inmuebles24" and casa["ubicacion"].startswith("Chapultepec")
    assert depto["tipo"] == "depto" and depto["operacion"] == "renta"
    assert ing.parsear_bloque("sin bloque") == []


def test_cambios_de_precio_y_bajas():
    ahora = datetime(2026, 11, 1, tzinfo=timezone.utc)
    existentes = {"u1": {"id": 1, "precio": 3e6}, "u2": {"id": 2, "precio": 2e6}}
    cambios = ing.cambios_de_precio(existentes, [{"url": "u1", "precio": 2.9e6}, {"url": "u2", "precio": 2e6},
                                                 {"url": "u3", "precio": 1e6}], ahora)
    assert cambios == [{"listing_id": 1, "fecha": ahora.isoformat(), "precio": 2.9e6}]
    vivos = [{"id": 1, "ultimo_visto": (ahora - timedelta(days=15)).isoformat(), "fecha_baja": None},
             {"id": 2, "ultimo_visto": (ahora - timedelta(days=3)).isoformat(), "fecha_baja": None}]
    assert ing.por_dar_de_baja(vivos, ahora) == [1]


def test_urls_portal_paginas():
    c = {"portales": {"inmuebles24": "https://www.inmuebles24.com/{tipo_i24}-en-venta-en-morelia.html"}}
    urls = ing.urls_portal(c, "casa", 2)
    assert urls == ["https://www.inmuebles24.com/casas-en-venta-en-morelia.html",
                    "https://www.inmuebles24.com/casas-en-venta-en-morelia-pagina-2.html"]


def test_extraccion_texto_esquema_fijo():
    v = extract_text.validar('Claro: {"conservacion": 7, "remodelada": "sí", "regimen": "Condominio", '
                             '"alberca": true, "cajones": "2", "precio": 5000000}')
    assert v == {"conservacion": None, "remodelada": True, "regimen": "condominio", "jardin": None,
                 "roof_garden": None, "seguridad_24h": None, "alberca": True, "cajones": 2}
    assert extract_text.validar("basura")["conservacion"] is None
    assert extract_text.hash_texto("Casa  Bonita") == extract_text.hash_texto("casa bonita")
