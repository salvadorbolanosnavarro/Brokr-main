"""Claude chat proxy extracted from the legacy main module.

The router receives a dependency-context callable so the progressive extraction
keeps resolving the same mutable main.py globals at request time. This preserves
legacy test/monkeypatch seams while the remaining monolith is decomposed.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


class ClaudeChatRequest(BaseModel):
    messages: list
    max_tokens: int = 1200
    context: str = ""


def create_router(get_context: Callable[[], dict[str, Any]]) -> APIRouter:
    router = APIRouter()

    @router.post("/chat-claude")
    async def chat_claude_proxy(req: ClaudeChatRequest, request: Request):
        deps = get_context()
        get_user_id_from_token = deps["get_user_id_from_token"]
        exigir_cupo = deps["exigir_cupo"]
        exigir_sesion = deps["exigir_sesion"]
        anthropic_api_key = deps["ANTHROPIC_API_KEY"]
        anthropic_base = deps["ANTHROPIC_BASE"]
        request_modulo = deps["_request_modulo"]
        track_anthropic = deps["_track_anthropic"]
        system_prompt = deps["SHAARK_SYSTEM_PROMPT"]

        uid = await get_user_id_from_token(request)
        exigir_cupo(request, uid)
        exigir_sesion(request, uid)
        if not anthropic_api_key:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")

        try:
            await get_user_id_from_token(request)
        except Exception as e:
            raise HTTPException(status_code=401, detail="No autenticado") from e

        modulo = (request_modulo(request) or "chat").lower()
        await track_anthropic(request, modulo)

        messages = [
            msg for msg in req.messages
            if isinstance(msg, dict) and msg.get("role") != "system"
        ]

        system = system_prompt
        if req.context:
            system += f"\n\nCONTEXTO DE LA PANTALLA ACTUAL:\n{req.context}"

        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": min(req.max_tokens, 4096),
            "system": system,
            "messages": messages,
            "tools": [{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3,
            }],
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{anthropic_base}/messages",
                headers={
                    "x-api-key": anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )

        if response.status_code != 200:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise HTTPException(status_code=response.status_code, detail=detail)

        data = response.json()
        content = data.get("content", [])
        text = ""
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")

        if not text:
            text = "Sin respuesta."

        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": text,
                }
            }]
        }

    return router
