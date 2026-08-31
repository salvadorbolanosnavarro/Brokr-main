"""Download endpoints for process-local generated PDFs."""
from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from core.pdf_store import _pdf_store


router = APIRouter()


def _streaming_pdf(token: str):
    if token not in _pdf_store:
        raise HTTPException(status_code=404, detail="PDF no encontrado o expirado")
    pdf_bytes, filename = _pdf_store[token]
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/pdf",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
        },
    )


@router.get("/avm-pdf/{token}")
async def descargar_avm_pdf(token: str):
    return _streaming_pdf(token)


@router.get("/isr-pdf/{token}")
async def descargar_isr_pdf(token: str):
    return _streaming_pdf(token)


@router.get("/ficha-pdf/{token}")
async def descargar_ficha_pdf(token: str):
    """Serve generated PDF by token — opens natively in Safari."""
    if token not in _pdf_store:
        raise HTTPException(status_code=404, detail="PDF no encontrado o expirado")
    pdf_bytes, filename = _pdf_store[token]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/pdf",
            "Cache-Control": "no-store",
        },
    )
