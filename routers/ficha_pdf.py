from __future__ import annotations

from fastapi import APIRouter, Request

from routers.ficha_pdf_core import generar_ficha_pdf_core


def create_router(get_context):
    router = APIRouter()

    @router.post("/ficha-pdf")
    async def generar_ficha_pdf(p: dict, request: Request):
        """Generate PDF from property data dict using Playwright."""
        deps = get_context()
        get_user_id_from_token = deps["get_user_id_from_token"]
        exigir_cupo = deps["exigir_cupo"]
        exigir_sesion = deps["exigir_sesion"]

        _uid = await get_user_id_from_token(request)
        exigir_cupo(request, _uid)
        exigir_sesion(request, _uid)

        token, filename = await generar_ficha_pdf_core(
            p,
            base64=deps["base64"],
            asyncio=deps["asyncio"],
            build_ficha_html=deps["build_ficha_html"],
            async_playwright=deps["async_playwright"],
            uuid=deps["_uuid"],
            pdf_store=deps["_pdf_store"],
        )

        from fastapi.responses import JSONResponse
        return JSONResponse({"token": token, "filename": filename})

    return router
