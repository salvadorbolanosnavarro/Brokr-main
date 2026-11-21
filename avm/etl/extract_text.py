"""Extracción de variables de la descripción del anuncio con el LLM.

El LLM SOLO extrae: devuelve JSON con un esquema fijo que se valida aquí
campo por campo (lo que no cumple se descarta). Nunca calcula valores.
Caché por hash SHA-256 de la descripción en avm_text_cache: la misma
descripción nunca se paga dos veces.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re

import httpx

from core.config import settings

log = logging.getLogger("broquer.avm_v2.texto")

ESQUEMA = {
    "conservacion": "entero 1-5 (5 = excelente/nuevo, 3 = bueno/normal, 1 = malo) o null",
    "remodelada": "true/false/null",
    "regimen": "'condominio' | 'privada' | 'independiente' | 'ejidal' | null",
    "jardin": "true/false/null",
    "roof_garden": "true/false/null",
    "seguridad_24h": "true/false/null",
    "alberca": "true/false/null",
    "cajones": "entero 0-20 o null",
}
REGIMENES = {"condominio", "privada", "independiente", "ejidal"}
PROMPT = (
    "Extrae datos de esta descripción de un anuncio inmobiliario en México. Responde SOLO un objeto JSON con "
    "exactamente estas llaves: " + json.dumps(ESQUEMA, ensure_ascii=False) + ". Usa null si el dato no aparece "
    "explícitamente. No inventes, no calcules precios, no agregues llaves.\n\nDescripción:\n"
)


def hash_texto(texto: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", texto.strip().lower()).encode()).hexdigest()


def _bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.lower() in ("true", "sí", "si", "yes"):
        return True
    if isinstance(v, str) and v.lower() in ("false", "no"):
        return False
    return None


def _entero(v, lo, hi):
    try:
        x = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return x if lo <= x <= hi else None


def validar(crudo) -> dict:
    """Fuerza el esquema fijo. Cualquier cosa fuera de rango → None."""
    if isinstance(crudo, str):
        m = re.search(r"\{.*\}", crudo, re.S)
        try:
            crudo = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            crudo = {}
    if not isinstance(crudo, dict):
        crudo = {}
    reg = crudo.get("regimen")
    reg = reg.strip().lower() if isinstance(reg, str) else None
    return {
        "conservacion": _entero(crudo.get("conservacion"), 1, 5),
        "remodelada": _bool(crudo.get("remodelada")),
        "regimen": reg if reg in REGIMENES else None,
        "jardin": _bool(crudo.get("jardin")),
        "roof_garden": _bool(crudo.get("roof_garden")),
        "seguridad_24h": _bool(crudo.get("seguridad_24h")),
        "alberca": _bool(crudo.get("alberca")),
        "cajones": _entero(crudo.get("cajones"), 0, 20),
    }


async def _llm(texto: str) -> tuple[str, str]:
    contenido = PROMPT + texto[:4000]
    async with httpx.AsyncClient(timeout=40) as c:
        if settings.groq_api_key:
            r = await c.post(f"{settings.groq_base}/chat/completions",
                             headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                             json={"model": settings.groq_extract_model, "temperature": 0,
                                   "response_format": {"type": "json_object"},
                                   "messages": [{"role": "user", "content": contenido}]})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"], settings.groq_extract_model
        if settings.anthropic_api_key:
            modelo = "claude-haiku-4-5"
            r = await c.post(f"{settings.anthropic_base}/v1/messages",
                             headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"},
                             json={"model": modelo, "max_tokens": 300, "temperature": 0,
                                   "messages": [{"role": "user", "content": contenido}]})
            r.raise_for_status()
            return r.json()["content"][0]["text"], modelo
    raise RuntimeError("Sin LLM configurado (GROQ_API_KEY o ANTHROPIC_API_KEY)")


async def extraer(texto: str) -> dict:
    from core.database import get_rows, upsert_rows
    h = hash_texto(texto)
    try:
        filas = await get_rows("avm_text_cache", {"hash_descripcion": f"eq.{h}", "limit": 1})
        if filas:
            return validar(filas[0]["extraido"])
    except Exception:
        pass
    crudo, modelo = await _llm(texto)
    datos = validar(crudo)
    try:
        await upsert_rows("avm_text_cache", [{"hash_descripcion": h, "extraido": datos, "modelo": modelo}],
                          conflict="hash_descripcion", prefer="return=minimal")
    except Exception as exc:
        log.info("No se guardó caché de texto: %s", exc)
    return datos


async def correr(limite: int = 300) -> dict:
    """Extrae variables de los anuncios con descripción y 'extra' vacío."""
    from core.database import patch_rows
    from .repo import leer_todo
    filas = await leer_todo("avm_listings", {"select": "id,descripcion,extra", "descripcion": "not.is.null",
                                             "extra": "eq.{}", "limit": limite})
    hechos = 0
    for f in filas[:limite]:
        if not (f.get("descripcion") or "").strip():
            continue
        try:
            datos = await extraer(f["descripcion"])
            await patch_rows("avm_listings", {"id": f"eq.{f['id']}"}, {"extra": datos})
            hechos += 1
        except Exception as exc:
            log.warning("Extracción falló en %s: %s", f["id"], exc)
    return {"procesados": hechos}


if __name__ == "__main__":
    print(asyncio.run(correr()))
