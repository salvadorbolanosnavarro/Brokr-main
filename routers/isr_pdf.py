"""ISR PDF generation endpoint."""
from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core.auth import get_user_id_from_token
from core.pdf_store import _pdf_store
from limites import exigir_cupo, exigir_sesion


router = APIRouter()


@router.post("/isr-pdf")
async def generar_isr_pdf(p: dict, request: Request):
    """Recibe HTML del cálculo ISR y lo convierte a PDF con Playwright."""
    _uid = await get_user_id_from_token(request)
    exigir_cupo(request, _uid)
    exigir_sesion(request, _uid)
    from playwright.async_api import async_playwright

    html = p.get("html", "")
    if not html:
        raise HTTPException(status_code=400, detail="HTML vacío")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        await page.set_content(html, wait_until="domcontentloaded")
        await page.wait_for_timeout(300)
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "20mm", "right": "20mm", "bottom": "20mm", "left": "20mm"},
        )
        await browser.close()
    token = str(_uuid.uuid4()).replace("-", "")[:16]
    filename = p.get("filename", "ISR_Brokr.pdf")
    _pdf_store[token] = (pdf_bytes, filename)
    if len(_pdf_store) > 50:
        oldest = list(_pdf_store.keys())[0]
        del _pdf_store[oldest]
    return JSONResponse({"token": token, "filename": filename})
