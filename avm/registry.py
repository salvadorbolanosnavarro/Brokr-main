"""Guardar, cargar y promover modelos.

Cada modelo es un solo archivo joblib (motores, tablas σ/δ/conformal,
referencia de comparables, contexto y métricas). Se guarda local (para cargar
rápido al arrancar) y en Supabase Storage (para sobrevivir a un redeploy de
Railway). 'actual.json' apunta al modelo promovido.
"""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import joblib

from core.config import settings

log = logging.getLogger("broquer.avm_v2")
PUNTERO = "actual.json"


def _dir() -> Path:
    d = Path(settings.avm_v2_model_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def guardar_local(modelo, metricas: dict | None = None) -> Path:
    ruta = _dir() / f"{modelo.version}.joblib"
    joblib.dump({"modelo": modelo, "metricas": metricas or {}}, ruta, compress=3)
    return ruta


def cargar_local(version: str | None = None):
    d = _dir()
    if version is None:
        p = d / PUNTERO
        if not p.exists():
            return None, {}
        version = json.loads(p.read_text())["version"]
    ruta = d / f"{version}.joblib"
    if not ruta.exists():
        return None, {}
    data = joblib.load(ruta)
    return data["modelo"], data.get("metricas", {})


def apuntar_local(version: str, metricas: dict) -> None:
    (_dir() / PUNTERO).write_text(json.dumps({"version": version, "metricas": metricas}, default=str))


async def subir(modelo, metricas: dict) -> bool:
    """Sube el artefacto y el puntero a Supabase Storage. Falla en silencio
    (log): el modelo local sigue sirviendo."""
    if not (settings.supabase_url and settings.supabase_service_key):
        return False
    try:
        from core.storage import upload_object
        buf = io.BytesIO()
        joblib.dump({"modelo": modelo, "metricas": metricas}, buf, compress=3)
        await upload_object(settings.avm_v2_bucket, f"{modelo.version}.joblib", buf.getvalue(),
                            content_type="application/octet-stream")
        return True
    except Exception as exc:          # pragma: no cover - depende de red
        log.warning("No se pudo subir el modelo %s: %s", modelo.version, exc)
        return False


async def promover_remoto(version: str, metricas: dict) -> None:
    if not (settings.supabase_url and settings.supabase_service_key):
        return
    try:
        from core.storage import upload_object
        await upload_object(settings.avm_v2_bucket, PUNTERO,
                            json.dumps({"version": version, "metricas": metricas}, default=str).encode(),
                            content_type="application/json")
    except Exception as exc:          # pragma: no cover
        log.warning("No se pudo actualizar el puntero remoto: %s", exc)


async def descargar_actual():
    """Baja el modelo promovido de Storage al disco local (arranque en frío)."""
    if not (settings.supabase_url and settings.supabase_service_key):
        return None, {}
    try:
        from core.storage import download_object
        puntero = json.loads((await download_object(settings.avm_v2_bucket, PUNTERO)).decode())
        datos = await download_object(settings.avm_v2_bucket, f"{puntero['version']}.joblib")
        (_dir() / f"{puntero['version']}.joblib").write_bytes(datos)
        apuntar_local(puntero["version"], puntero.get("metricas", {}))
        return cargar_local(puntero["version"])
    except Exception as exc:          # pragma: no cover
        log.info("Sin modelo remoto todavía: %s", exc)
        return None, {}


def decidir_promocion(nuevo: dict, actual: dict | None, max_empeora_pts: float) -> tuple[bool, str]:
    """Promueve salvo que el MdAPE empeore más de N puntos frente al actual."""
    if not actual or actual.get("mdape") is None:
        return True, "no hay modelo anterior con métricas"
    if nuevo.get("mdape") is None:
        return False, "el modelo nuevo no tiene MdAPE"
    if nuevo["mdape"] > actual["mdape"] + max_empeora_pts:
        return False, f"MdAPE empeora de {actual['mdape']} a {nuevo['mdape']}"
    return True, f"MdAPE {actual['mdape']} → {nuevo['mdape']}"
