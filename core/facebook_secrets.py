"""Facebook/Meta secret-at-rest encryption with legacy plaintext read compatibility."""
from __future__ import annotations

import logging

from fastapi import HTTPException

from core.legacy_main_config import legacy_main_settings


_PREFIX = "enc:v1:"
_TOKEN_ENC_KEY = legacy_main_settings.token_enc_key
_LOG = logging.getLogger("broquer.facebook")

try:
    from cryptography.fernet import Fernet, InvalidToken
    _FERNET = Fernet(_TOKEN_ENC_KEY.encode()) if _TOKEN_ENC_KEY else None
except Exception as exc:
    _FERNET = None
    InvalidToken = Exception  # type: ignore
    if _TOKEN_ENC_KEY:
        _LOG.error(
            "TOKEN_ENC_KEY inválida (%s). Las nuevas escrituras de tokens de Meta se rechazarán hasta corregirla. "
            "Genera una con: python3 -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"",
            exc,
        )


def facebook_secret_encryption_available() -> bool:
    return _FERNET is not None


def encrypt_facebook_secret(value: str) -> str:
    """Encrypt a new Meta secret; never fall back to plaintext writes."""
    if not value:
        return value
    if value.startswith(_PREFIX):
        return value
    if not _FERNET:
        raise HTTPException(
            status_code=503,
            detail="Cifrado de tokens de Meta no disponible. Configura TOKEN_ENC_KEY.",
        )
    try:
        return _PREFIX + _FERNET.encrypt(value.encode("utf-8")).decode("ascii")
    except Exception as exc:
        _LOG.error("No se pudo cifrar el token: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="No se pudo proteger el token de Meta. Intenta de nuevo más tarde.",
        ) from exc


def decrypt_facebook_secret(value: str) -> str:
    """Decrypt encrypted values while retaining reads of pre-encryption plaintext rows."""
    if not value or not isinstance(value, str):
        return value or ""
    if not value.startswith(_PREFIX):
        return value
    if not _FERNET:
        _LOG.error(
            "Hay tokens cifrados en la base pero TOKEN_ENC_KEY no está configurada. "
            "Restaura la llave o el usuario tendrá que reconectar Facebook."
        )
        return ""
    try:
        return _FERNET.decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        _LOG.error(
            "Token cifrado con OTRA llave (TOKEN_ENC_KEY cambió). "
            "El usuario tendrá que reconectar Facebook."
        )
        return ""
    except Exception as exc:
        _LOG.error("No se pudo descifrar el token: %s", exc)
        return ""
