"""Standard DOCX contract generation with optional AI-drafted clauses."""
from __future__ import annotations

import json as _json
import os
from pathlib import Path
import subprocess
import tempfile

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
from core.telemetry import _track_groq


router = APIRouter()
_ROOT = Path(__file__).resolve().parents[1]


class ContratoRequest(BaseModel):
    tipo: str
    datos: dict
    clausulas_especiales: list = []


@router.post("/contrato")
async def generar_contrato(req: ContratoRequest, request: Request):
    """Generate a DOCX contract from form data, with AI-drafted special clauses."""
    user_id = await get_user_id_from_token(request)

    clausulas_redactadas = []
    if req.clausulas_especiales:
        tipo_label = "arrendamiento" if req.tipo == "arrendamiento" else "promesa de compraventa"
        lista_clausulas = "\n".join(f"{i+1}. {c}" for i, c in enumerate(req.clausulas_especiales))
        prompt_clausulas = (
            "Eres un abogado especialista en derecho inmobiliario mexicano con 20 años de experiencia "
            "redactando contratos conforme al Código Civil Federal y los códigos civiles estatales.\n\n"
            f"El usuario quiere incluir las siguientes cláusulas especiales en un contrato de {tipo_label}. "
            "Para cada una, redacta una cláusula jurídicamente correcta, con lenguaje formal, precisa y "
            "ejecutable ante tribunales mexicanos. Usa numeración romana (PRIMERA ESPECIAL, SEGUNDA ESPECIAL, etc.).\n\n"
            "No incluyas explicaciones ni comentarios — solo la cláusula redactada lista para insertarse en el contrato.\n\n"
            "Cláusulas a redactar:\n"
            + lista_clausulas
        )

        try:
            headers = {
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt_clausulas}],
                "max_tokens": 2000,
                "temperature": 0.3,
            }
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
            if r.status_code == 200:
                resp_json = r.json()
                _track_groq(
                    user_id,
                    "contratos",
                    "/contrato",
                    resp_json,
                    modelo=payload.get("model") or "llama-3.3-70b-versatile",
                )
                ai_text = resp_json["choices"][0]["message"]["content"].strip()
                clausulas_redactadas = [ai_text]
        except Exception as e:
            print(f"AI clause drafting error: {e}")
            clausulas_redactadas = req.clausulas_especiales

    datos_completos = dict(req.datos)
    datos_completos["clausulas_especiales"] = clausulas_redactadas

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        _json.dump(datos_completos, f, ensure_ascii=False)
        json_path = f.name

    output_path = json_path.replace(".json", ".docx")

    try:
        script = os.fspath(_ROOT / "generar_contrato.py")
        result = subprocess.run(
            ["python3", script, req.tipo, json_path, output_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Error generando contrato: {result.stderr}")

        nombres = {
            "arrendamiento": "Contrato_Arrendamiento.docx",
            "promesa": "Promesa_Compraventa.docx",
        }
        filename = nombres.get(req.tipo, "Contrato.docx")

        return FileResponse(
            output_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
            background=None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            os.unlink(json_path)
        except Exception:
            pass
