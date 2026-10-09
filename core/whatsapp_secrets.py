"""Cifrado en reposo de los tokens de Meta de WhatsApp.

Cubre las dos tablas que guardan un token de WhatsApp en `access_token`:
`wa2_numeros` (WhatsApp principal) y `wac_numbers` (WhatsApp de ChatGPT).

Reglas para que nadie se desconecte:
  · Leer: un token cifrado (empieza con "enc:wa1:") se descifra; un token
    viejo en texto plano se usa tal cual.
  · Escribir: si WA_TOKEN_ENC_KEY existe, el token se guarda cifrado; si no
    existe, se guarda como hoy (texto plano). Nunca se cifra dos veces.
  · La llave puede ser cualquier texto largo: se deriva con SHA-256.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any, Iterable

from cryptography.fernet import Fernet, InvalidToken

from core.config import settings


PREFIX = "enc:wa1:"
TABLAS_CON_TOKEN = frozenset({"wa2_numeros", "wac_numbers"})
_LOG = logging.getLogger("broquer.whatsapp.tokens")


def _fernet_desde(llave: str) -> Fernet | None:
    llave = (llave or "").strip()
    if not llave:
        return None
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(llave.encode("utf-8")).digest()))


_FERNET = _fernet_desde(settings.wa_token_enc_key)


def cifrado_disponible() -> bool:
    return _FERNET is not None


def esta_cifrado(valor: Any) -> bool:
    return isinstance(valor, str) and valor.startswith(PREFIX)


def cifrar_token(valor: Any, *, fernet: Fernet | None = None) -> Any:
    """Cifra un token nuevo. Sin llave, o si ya está cifrado, lo deja igual."""
    f = fernet or _FERNET
    if not valor or not isinstance(valor, str) or esta_cifrado(valor) or f is None:
        return valor
    return PREFIX + f.encrypt(valor.encode("utf-8")).decode("ascii")


def descifrar_token(valor: Any, *, fernet: Fernet | None = None) -> Any:
    """Descifra un token cifrado; un token viejo en texto plano pasa igual."""
    if not esta_cifrado(valor):
        return valor
    f = fernet or _FERNET
    if f is None:
        _LOG.error("Hay tokens de WhatsApp cifrados pero falta WA_TOKEN_ENC_KEY en el servidor.")
        return ""
    try:
        return f.decrypt(valor[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        _LOG.error("Token de WhatsApp cifrado con OTRA llave (WA_TOKEN_ENC_KEY cambió).")
        return ""


def proteger_para_guardar(tabla: str, cuerpo: Any) -> Any:
    """Copia del cuerpo con el token cifrado, solo para las tablas con token."""
    if tabla not in TABLAS_CON_TOKEN:
        return cuerpo
    if isinstance(cuerpo, list):
        return [proteger_para_guardar(tabla, fila) for fila in cuerpo]
    if isinstance(cuerpo, dict) and cuerpo.get("access_token"):
        copia = dict(cuerpo)
        copia["access_token"] = cifrar_token(copia["access_token"])
        return copia
    return cuerpo


def revelar_filas(tabla: str, filas: Any) -> Any:
    """Descifra `access_token` en las filas leídas de las tablas con token."""
    if tabla not in TABLAS_CON_TOKEN or not isinstance(filas, list):
        return filas
    for fila in filas:
        if isinstance(fila, dict) and esta_cifrado(fila.get("access_token")):
            fila["access_token"] = descifrar_token(fila["access_token"])
    return filas


def plan_de_conversion(filas: Iterable[dict], accion: str, *, fernet: Fernet | None = None) -> list[tuple[Any, str, str]]:
    """(id, valor_actual, valor_nuevo) para cada fila que hay que convertir."""
    f = fernet or _FERNET
    if f is None or accion not in ("cifrar", "descifrar"):
        return []
    cambios = []
    for fila in filas:
        actual = fila.get("access_token")
        if not actual or not isinstance(actual, str) or fila.get("id") is None:
            continue
        if accion == "cifrar" and not esta_cifrado(actual):
            cambios.append((fila["id"], actual, cifrar_token(actual, fernet=f)))
        elif accion == "descifrar" and esta_cifrado(actual):
            claro = descifrar_token(actual, fernet=f)
            if claro:
                cambios.append((fila["id"], actual, claro))
    return cambios
