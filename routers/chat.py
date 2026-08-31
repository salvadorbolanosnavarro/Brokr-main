"""Groq chat proxy."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
from core.telemetry import _request_modulo, _track_groq
from limites import exigir_cupo, exigir_sesion


router = APIRouter()
GROQ_API_KEY = settings.groq_api_key
GROQ_BASE = "https://api.groq.com/openai/v1"


class ChatRequest(BaseModel):
    messages: list
    model: str = "llama-3.3-70b-versatile"
    max_tokens: int = 1024
    temperature: float = 0.7


@router.post("/chat")
async def chat_proxy(req: ChatRequest, request: Request):
    _uid = await get_user_id_from_token(request)
    exigir_cupo(request, _uid)
    exigir_sesion(request, _uid)
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY no configurada en el servidor")
    user_id = await get_user_id_from_token(request)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{GROQ_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": req.model,
                "messages": req.messages,
                "max_tokens": req.max_tokens,
                "temperature": req.temperature,
            },
        )
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=f"Error Groq: {r.text}")
        data = r.json()
        _track_groq(
            user_id,
            _request_modulo(request, "chat"),
            "/chat",
            data,
            modelo=req.model or "llama-3.3-70b-versatile",
        )
        return data
