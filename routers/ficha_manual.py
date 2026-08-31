"""Manual property-sheet AI helpers."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.telemetry import _track_anthropic
from limites import exigir_cupo, exigir_sesion


router = APIRouter()
ANTHROPIC_API_KEY = settings.anthropic_api_key
ANTHROPIC_BASE = "https://api.anthropic.com/v1"


@router.post("/ficha-manual/descripcion")
async def generar_descripcion_ficha_manual(data: dict, request: Request):
    """Generate AI description for ficha manual — uses same httpx pattern as rest of backend."""
    _uid = await get_user_id_from_token(request)
    exigir_cupo(request, _uid)
    exigir_sesion(request, _uid)
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")
    user_id = await get_user_id_from_token(request)

    tipo = data.get("tipo", "")
    colonia = data.get("colonia", "")
    ciudad = data.get("ciudad", "Morelia")
    m2c = data.get("m2c", "")
    m2t = data.get("m2t", "")
    rec = data.get("rec", "")
    ban = data.get("ban", "")
    est = data.get("est", "")
    niv = data.get("niv", "")
    anio = data.get("anio", "")
    precio = data.get("precio", "")
    op = data.get("op", "Venta")
    amen = data.get("amen", "")

    partes = []
    if tipo: partes.append(f"Tipo: {tipo}")
    if op: partes.append(f"Operación: {op}")
    if precio: partes.append(f"Precio: {precio}")
    if colonia: partes.append(f"Colonia: {colonia}, {ciudad}")
    if rec: partes.append(f"Recámaras: {rec}")
    if ban: partes.append(f"Baños: {ban}")
    if m2c: partes.append(f"Construcción: {m2c} m²")
    if m2t: partes.append(f"Terreno: {m2t} m²")
    if est: partes.append(f"Estacionamientos: {est}")
    if niv: partes.append(f"Niveles: {niv}")
    if anio: partes.append(f"Año: {anio}")
    if amen: partes.append(f"Amenidades: {amen}")

    ficha_info = "\n".join(partes) if partes else "Propiedad sin datos"
    prompt = (
        "Eres un redactor especialista en bienes raíces en México. "
        "Escribe una descripción comercial atractiva, profesional y fluida "
        "de máximo 120 palabras para la siguiente propiedad. "
        "Sin bullets, sin encabezados, solo prosa natural y persuasiva. "
        "No repitas datos de forma robótica; hazlo sonar humano y apetecible.\n\n"
        f"{ficha_info}"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 350,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Error IA: {r.status_code}")
    resp = r.json()
    _track_anthropic(
        user_id,
        "ficha-manual",
        "/ficha-manual/descripcion",
        resp,
        modelo=resp.get("model") or "claude-sonnet-4-6",
    )
    descripcion = resp.get("content", [{}])[0].get("text", "").strip()
    return {"descripcion": descripcion}
