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
            if modelo is None and settings.avm_v2_demo:
                # Solo staging: modelo de demostración con datos sintéticos,
                # marcado como tal en cada respuesta.
                from . import pipeline, synthetic
                m = await asyncio.to_thread(synthetic.generar, 1500)
                modelo, _ = await asyncio.to_thread(pipeline.entrenar, m.listings, m.closings, m.indice,
                                                    synthetic.FECHA_FIN, "sinteticos", None, 300)
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


async def geocodificar(direccion: str) -> tuple[float, float, str] | None:
    """Dirección → (lat, lon, precisión). Usa la llave de Google que ya tiene
    el módulo de colonias. ROOFTOP = exacta; lo demás, aproximada."""
    if not settings.google_places_key or not direccion.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(GEOCODE_URL, params={"address": direccion, "region": "mx", "language": "es",
                                                      "key": settings.google_places_key})
        data = r.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        res = data["results"][0]
        loc = res["geometry"]["location"]
        precision = "exacta" if res["geometry"].get("location_type") == "ROOFTOP" else "aproximada"
        return float(loc["lat"]), float(loc["lng"]), precision
    except Exception as exc:      # pragma: no cover - red
        log.info("Geocodificación falló: %s", exc)
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
        "tipo_documento": "Opinión Comercial de Valor",
    }
