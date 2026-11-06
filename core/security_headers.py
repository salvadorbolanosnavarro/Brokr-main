"""Cabeceras de seguridad comunes a todas las respuestas de la API.

``X-Content-Type-Options: nosniff`` impide que el navegador "adivine" que un
archivo es una página web y la ejecute: se respeta el Content-Type declarado.
Es la defensa de fondo para cualquier archivo que sirva la API (PDF de fichas,
contratos, constancias, etc.).
"""
from __future__ import annotations


def instalar_cabeceras_seguras(app) -> None:
    @app.middleware("http")
    async def _cabeceras_seguras(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response
