"""
Límite de peticiones para los endpoints que cuestan dinero.

POR QUÉ EXISTE
Los endpoints de IA (Broq, AVM, descripciones, transcripción) y los que
levantan un navegador para generar PDF pueden tener un costo material. Este
módulo limita abuso y concentra la política de sesión que protege esas rutas.

CÓMO FUNCIONA
Una ventana deslizante de una hora, en memoria. A quien viene con sesión se le
cuenta por usuario y se le da un tope amplio. Mientras la compatibilidad legacy
mantenga habilitado el acceso anónimo, a quien viene sin sesión se le cuenta
por dirección IP y se le aplica un tope corto.

La configuración vive en core.config. ``EXIGIR_SESION_IA`` conserva por ahora
su comportamiento histórico (apagado si no se define) para no romper clientes
legacy sin verificar antes su estado, pero el modo anónimo queda señalado de
forma explícita en logs para que no pase inadvertido.

LÍMITES CONOCIDOS
Vive en la memoria del proceso. Con varias instancias cada una lleva su propia
cuenta; por tanto este mecanismo mitiga abuso, pero no es un medidor distribuido
ni una base adecuada para facturación por uso.
"""

import logging
import time
from collections import deque

from fastapi import HTTPException, Request

from core.config import settings

log = logging.getLogger("broquer.limites")

TOPE_ANONIMO = settings.hourly_anonymous_limit
TOPE_USUARIO = settings.hourly_user_limit
VENTANA = 3600  # una hora, en segundos

if not settings.ai_require_session:
    log.warning(
        "EXIGIR_SESION_IA está desactivado: endpoints costosos protegidos por "
        "limites.py todavía pueden aceptar tráfico anónimo por compatibilidad legacy."
    )

_marcas: dict[str, deque] = {}
_ultima_limpieza = 0.0


def _llave(request: Request, user_id: str | None) -> tuple[str, int]:
    """Devuelve con qué identificador se cuenta y cuál es su tope."""
    if user_id:
        return f"u:{user_id}", TOPE_USUARIO

    # Railway entrega la IP real en x-forwarded-for. Este valor solo debe
    # considerarse una señal de rate limiting, nunca una identidad/autorización.
    reenviada = request.headers.get("x-forwarded-for", "")
    if reenviada:
        ip = reenviada.split(",")[0].strip()
    elif request.client:
        ip = request.client.host
    else:
        ip = "desconocida"
    return f"ip:{ip}", TOPE_ANONIMO


def _limpiar(ahora: float) -> None:
    """Descarta llaves sin marcas vivas para limitar el crecimiento en memoria."""
    global _ultima_limpieza
    if ahora - _ultima_limpieza < 300:
        return
    _ultima_limpieza = ahora
    for llave in list(_marcas.keys()):
        cola = _marcas[llave]
        while cola and cola[0] < ahora - VENTANA:
            cola.popleft()
        if not cola:
            _marcas.pop(llave, None)


def exigir_cupo(request: Request, user_id: str | None = None) -> None:
    """Cuenta esta petición y corta con 429 si ya se pasó del tope."""
    ahora = time.time()
    _limpiar(ahora)

    llave, tope = _llave(request, user_id)
    cola = _marcas.setdefault(llave, deque())

    while cola and cola[0] < ahora - VENTANA:
        cola.popleft()

    if len(cola) >= tope:
        espera = int(cola[0] + VENTANA - ahora) + 1
        raise HTTPException(
            status_code=429,
            detail="Demasiadas peticiones seguidas. Espera un momento y vuelve a intentar.",
            headers={"Retry-After": str(max(1, espera))},
        )

    cola.append(ahora)


def exigir_sesion(request: Request, user_id: str | None) -> None:
    """Exige sesión cuando la política canónica lo tiene habilitado.

    El valor se resuelve una sola vez desde ``core.config`` al arrancar el
    proceso. Para cambiarlo en producción se actualiza ``EXIGIR_SESION_IA`` y
    se reinicia/re despliega el servicio, evitando que la política cambie a
    mitad de vida del proceso.
    """
    if user_id:
        return
    if settings.ai_require_session:
        raise HTTPException(status_code=401, detail="Inicia sesión para usar esta función.")
