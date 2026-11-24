"""El modelo vive en memoria: se carga una vez al arrancar (local → Storage →
demo sintética si AVM_V2_DEMO) y cada estimación tarda milisegundos."""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import httpx

from core.config import settings

from . import registry

log = logging.getLogger("broquer.avm_v2")
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def _en_vivo_disponible() -> bool:
    from core.legacy_main_config import legacy_main_settings
    return bool(legacy_main_settings.firecrawl_api_key and settings.google_places_key)


class Servicio:
    def __init__(self):
        self.modelo = None
        self.metricas: dict = {}
        self.estado = "sin_cargar"
        self._lock = asyncio.Lock()

    async def cargar(self) -> None:
        async with self._lock:
            if self.modelo is not None:
                return
            modelo, met = await asyncio.to_thread(registry.cargar_local)
            if modelo is None:
                modelo, met = await registry.descargar_actual()
            if modelo is None and settings.avm_v2_demo and not _en_vivo_disponible():
                # Solo staging: modelo de demostración con datos sintéticos,
                # marcado como tal en cada respuesta.
                from . import pipeline, synthetic
                m = await asyncio.to_thread(synthetic.generar, 2500, 11, 0.06, 0.015, 160, True)
                ageb = synthetic.agebs_contexto()
                modelo, _ = await asyncio.to_thread(pipeline.entrenar, m.listings, m.closings, m.indice,
                                                    synthetic.FECHA_FIN, "sinteticos",
                                                    {"ageb": ageb} if ageb is not None else None, 300)
                met = {"nota": "demo sintética"}
            self.modelo, self.metricas = modelo, met or {}
            self.estado = "listo" if modelo is not None else "sin_modelo"
            log.info("AVM v2: %s (%s)", self.estado, getattr(modelo, "version", "-"))

    def reemplazar(self, modelo, metricas: dict) -> None:
        self.modelo, self.metricas, self.estado = modelo, metricas, "listo"

    def info(self) -> dict:
        m = self.modelo
        return {"estado": self.estado, "version": getattr(m, "version", None), "datos": getattr(m, "datos", None),
                "fecha_valuacion": str(getattr(m, "fecha_valuacion", "") or "")[:10] or None,
                "metricas": self.metricas}

    def estimar(self, sujeto: dict) -> dict:
        return _limpiar_salida(self.modelo.estimar(sujeto))


servicio = Servicio()


FINDPLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
# Resultados que solo ubican una ciudad o estado: no sirven para valuar.
TIPOS_DEMASIADO_AMPLIOS = {"locality", "administrative_area_level_1", "administrative_area_level_2",
                           "administrative_area_level_3", "country", "postal_town", "colloquial_area"}
TIPOS_EXACTOS = {"street_address", "premise", "subpremise"}


class UbicacionAmplia(Exception):
    """La dirección solo identifica una ciudad o estado."""


def _precision(tipos: set[str], location_type: str = "") -> str:
    if location_type == "ROOFTOP" or tipos & TIPOS_EXACTOS:
        return "exacta"
    return "aproximada"


def _es_amplia(tipos: set[str]) -> bool:
    return bool(tipos) and tipos <= (TIPOS_DEMASIADO_AMPLIOS | {"political"})


async def geocodificar(direccion: str) -> tuple[float, float, str] | None:
    """Dirección → (lat, lon, precisión) con la llave de Google del módulo de
    colonias. Primero Geocoding; si esa API no está habilitada en la llave o no
    encuentra nada, Places (la misma API que ya usa el buscador de colonias).
    Lanza UbicacionAmplia si lo escrito es solo una ciudad."""
    if not settings.google_places_key or not direccion.strip():
        return None
    texto = direccion.strip()
    if "mex" not in texto.lower():
        texto += ", México"
    amplia = False
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            r = await client.get(GEOCODE_URL, params={"address": texto, "region": "mx", "language": "es",
                                                      "key": settings.google_places_key})
            data = r.json()
            if data.get("status") == "OK" and data.get("results"):
                res = data["results"][0]
                tipos = set(res.get("types") or [])
                if _es_amplia(tipos):
                    amplia = True
                else:
                    loc = res["geometry"]["location"]
                    return float(loc["lat"]), float(loc["lng"]), _precision(tipos, res["geometry"].get("location_type", ""))
            else:
                log.info("Geocoding sin resultado (%s); se intenta Places", data.get("status"))
        except Exception as exc:      # pragma: no cover - red
            log.info("Geocoding falló: %s", exc)
        try:
            r = await client.get(FINDPLACE_URL, params={"input": texto, "inputtype": "textquery", "language": "es",
                                                        "fields": "geometry,types",
                                                        "key": settings.google_places_key})
            data = r.json()
            cands = data.get("candidates") or []
            if data.get("status") == "OK" and cands:
                tipos = set(cands[0].get("types") or [])
                if _es_amplia(tipos):
                    amplia = True
                else:
                    loc = cands[0]["geometry"]["location"]
                    return float(loc["lat"]), float(loc["lng"]), _precision(tipos)
            else:
                log.info("Places sin resultado (%s)", data.get("status"))
        except Exception as exc:      # pragma: no cover - red
            log.info("Places falló: %s", exc)
    if amplia:
        raise UbicacionAmplia(direccion)
    return None


def _num(v: Any):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _limpiar_salida(r: dict) -> dict:
    """Respuesta pública: números redondeados, comparables solo con enlace
    consultado, sin campos internos."""
    redondea = lambda v: None if v is None else int(round(v / 1000.0) * 1000)
    comps = []
    for c in r.get("comparables", []):
        if not c.get("url"):
            continue
        comps.append({"url": c["url"], "precio": redondea(c["precio"]), "m2": round(c["m2"], 1),
                      "precio_m2": int(round(c["precio_m2"])), "distancia_m": c["dist_m"],
                      "peso": c["peso"], "factor_homologacion": c["factor_total"]})
    motores = {}
    for k, m in r["motores"].items():
        motores[k] = {"nombre": m["nombre"], "calculado": m["ok"], "valor": redondea(m["valor"]) if m["ok"] else None,
                      "peso": m.get("peso", 0.0), "motivo": m.get("motivo") or None}
        if k == "C" and m["ok"]:
            d = m.get("detalle") or {}
            motores[k]["desglose"] = {"terreno": redondea(d.get("valor_terreno")),
                                      "construccion": redondea(d.get("valor_construccion"))}
    return {
        "emitido": r["emitido"],
        "valor": redondea(r["valor"]),
        "rango": [redondea(r["rango"][0]), redondea(r["rango"][1])] if r["rango"] else None,
        "confianza": r["confianza"],
        "ancho_rango_pct": round(100 * r["ancho_relativo"], 1) if r.get("ancho_relativo") is not None else None,
        "descuento_negociacion_pct": round(100 * r["delta"], 1),
        "motores": motores,
        "comparables": comps,
        "explicacion": r["explicacion"],
        "advertencias": r["advertencias"],
        "version": r["version"],
        "datos": r["datos"],
        "anuncios_leidos": r.get("anuncios_leidos"),
        "tipo_documento": "Opinión Comercial de Valor",
    }
