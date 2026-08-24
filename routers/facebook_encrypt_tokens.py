"""Facebook token-at-rest migration for an authorized Broquer organization member."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from core.facebook_connection_store import get_facebook_meta_row, patch_facebook_meta
from core.facebook_secrets import facebook_secret_encryption_available
from routers.organizaciones import exigir_gestion_integraciones


router = APIRouter()


@router.post("/facebook/encrypt-tokens")
async def facebook_encrypt_tokens(request: Request):
    """Cifra tokens legacy en texto plano mediante una reescritura idempotente."""
    user_id = await exigir_gestion_integraciones(request)
    if not facebook_secret_encryption_available():
        raise HTTPException(
            status_code=503,
            detail="Falta configurar TOKEN_ENC_KEY en el servidor. Genera una con: "
            "python3 -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"",
        )

    fila = await get_facebook_meta_row(user_id)
    if not fila:
        raise HTTPException(status_code=400, detail="No hay conexión de Facebook.")

    await patch_facebook_meta(
        user_id,
        {"tokens_cifrados_at": datetime.now(timezone.utc).isoformat()},
    )
    return {
        "ok": True,
        "mensaje": "Tus tokens de Facebook quedaron cifrados en reposo.",
    }
