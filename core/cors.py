"""CORS de la API: quién puede llamarla desde un navegador.

Dos modos, elegidos con CORS_MODO en Railway:
  · "observar" (default, también si la variable no existe): acepta cualquier
    origen, igual que antes, pero anota en los logs cada origen que NO está
    en la lista. Sirve para confirmar la lista sin romper nada.
  · "estricto": solo acepta los orígenes de la lista.

CORS_ORIGENES_EXTRA (separados por coma) agrega orígenes sin tocar código.
Las llamadas de servidores (Meta, Stripe, Cloudflare, Zapier…) no mandan
Origin y no les afecta ningún modo.
"""
from __future__ import annotations

import logging

from fastapi.middleware.cors import CORSMiddleware

from core.config import settings


ORIGENES_CONOCIDOS = (
    "https://broquer.app",
    "https://www.broquer.app",
    "https://staging.broquer.app",
    # App de iOS (Capacitor). La configuración actual usa capacitor://;
    # los otros dos cubren otras configuraciones de Capacitor/Ionic.
    "capacitor://localhost",
    "https://localhost",
    "ionic://localhost",
    # Dominios antiguos: se quitan después de revisar los logs.
    "https://navarroai.github.io",
    "https://app.navarroai.com.mx",
)
_TOPE_ANOTADOS = 500
log = logging.getLogger("broquer.cors")


def _normaliza(origen: str) -> str:
    return (origen or "").strip().rstrip("/").lower()


def origenes_permitidos(extra: str | None = None) -> list[str]:
    extra = settings.cors_origenes_extra if extra is None else extra
    lista = [_normaliza(o) for o in ORIGENES_CONOCIDOS]
    for origen in (extra or "").split(","):
        origen = _normaliza(origen)
        if origen and origen not in lista:
            lista.append(origen)
    return lista


def modo_estricto(modo: str | None = None) -> bool:
    return (settings.cors_modo if modo is None else modo).strip().lower() == "estricto"


class ObservarOrigenes:
    """Middleware ASGI que solo anota (una vez) los orígenes fuera de la lista."""

    def __init__(self, app, permitidos: list[str]):
        self.app = app
        self.permitidos = frozenset(permitidos)
        self.anotados: set[str] = set()

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            for nombre, valor in scope.get("headers") or ():
                if nombre == b"origin":
                    origen = _normaliza(valor.decode("latin-1"))
                    if (origen and origen not in self.permitidos and origen not in self.anotados
                            and len(self.anotados) < _TOPE_ANOTADOS):
                        self.anotados.add(origen)
                        log.warning("CORS origen no listado: %s (ruta %s)", origen, scope.get("path", ""))
                    break
        await self.app(scope, receive, send)


def instalar_cors(app) -> None:
    permitidos = origenes_permitidos()
    if modo_estricto():
        app.add_middleware(
            CORSMiddleware,
            allow_origins=permitidos,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        log.warning("CORS en modo ESTRICTO: %d orígenes permitidos.", len(permitidos))
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ObservarOrigenes, permitidos=permitidos)
    log.warning("CORS en modo OBSERVAR: acepta todo y anota orígenes fuera de la lista.")
