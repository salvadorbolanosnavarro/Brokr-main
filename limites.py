"""
Límite de peticiones para los endpoints que cuestan dinero.

POR QUÉ EXISTE
Los endpoints de IA (Broq, AVM, descripciones, transcripción) y los que
levantan un navegador para generar PDF responden a cualquiera en internet.
Sin un tope, una sola persona puede dejar corriendo un script toda la noche y
amanecer con una cuenta de Anthropic impagable.

CÓMO FUNCIONA
Una ventana deslizante de una hora, en memoria. A quien viene con sesión se le
cuenta por usuario y se le da un tope amplio. A quien viene sin sesión se le
cuenta por dirección IP y se le da un tope corto: suficiente para que la app de
iOS que todavía no manda el token siga funcionando con normalidad, pero muy
lejos de lo que necesitaría alguien para abusar.

LÍMITES CONOCIDOS
Vive en la memoria del proceso. Si algún día corren dos instancias en Railway,
cada una lleva su propia cuenta y el tope real se duplica. Para lo que hace
falta aquí —cortar el abuso automatizado, no cobrar por uso— alcanza y sobra.
Se reinicia en cada despliegue, cosa que tampoco importa.
"""

import os
import time
from collections import deque

from fastapi import HTTPException, Request

# Topes por hora. Se pueden ajustar desde Railway sin tocar código.
try:
    TOPE_ANONIMO = max(1, int(os.environ.get("TOPE_HORA_ANONIMO", "40")))
except Exception:
    TOPE_ANONIMO = 40
try:
    TOPE_USUARIO = max(1, int(os.environ.get("TOPE_HORA_USUARIO", "400")))
except Exception:
    TOPE_USUARIO = 400

VENTANA = 3600  # una hora, en segundos

_marcas: dict[str, deque] = {}
_ultima_limpieza = 0.0


def _llave(request: Request, user_id: str | None) -> tuple[str, int]:
    """Devuelve con qué identificador se cuenta y cuál es su tope."""
    if user_id:
        return f"u:{user_id}", TOPE_USUARIO

    # Railway entrega la IP real en x-forwarded-for; request.client sería la
    # del proxy y contaría a todo el mundo junto.
    reenviada = request.headers.get("x-forwarded-for", "")
    if reenviada:
        ip = reenviada.split(",")[0].strip()
    elif request.client:
        ip = request.client.host
    else:
        ip = "desconocida"
    return f"ip:{ip}", TOPE_ANONIMO


def _limpiar(ahora: float) -> None:
    """Tira las llaves que ya no tienen marcas vivas, para que el diccionario
    no crezca sin fin. Se hace de vez en cuando, no en cada petición."""
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
    """Cuenta esta petición y corta con 429 si ya se pasó del tope.

    No devuelve nada: o deja pasar, o levanta la excepción.
    """
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
    """Corta si no hay sesión, PERO solo cuando el interruptor está encendido.

    El interruptor es la variable EXIGIR_SESION_IA en Railway. Existe porque la
    app de iOS lleva el JavaScript dentro del paquete: hasta que la versión
    nueva no esté publicada y actualizada, un usuario con la app vieja no manda
    la sesión y se quedaría sin Broq. Con esto se enciende el día que convenga,
    sin volver a desplegar, y se apaga igual de rápido si algo sale mal.

    Apagado (por omisión) el tope por hora sigue actuando, así que el abuso
    sigue acotado aunque todavía no se exija sesión.
    """
    if user_id:
        return
    encendido = os.environ.get("EXIGIR_SESION_IA", "").strip().lower() in ("1", "true", "si", "sí", "on")
    if encendido:
        raise HTTPException(status_code=401, detail="Inicia sesión para usar esta función.")
