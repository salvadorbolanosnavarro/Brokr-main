from __future__ import annotations

from fastapi import APIRouter, Request


def create_router(get_context):
    router = APIRouter()

    @router.post("/ficha-pdf")
    async def generar_ficha_pdf(p: dict, request: Request):
        """Generate PDF from property data dict using Playwright."""
        deps = get_context()
        get_user_id_from_token = deps["get_user_id_from_token"]
        exigir_cupo = deps["exigir_cupo"]
        exigir_sesion = deps["exigir_sesion"]
        base64_mod = deps["base64"]
        asyncio_mod = deps["asyncio"]
        build_ficha_html = deps["build_ficha_html"]
        async_playwright = deps["async_playwright"]
        uuid_mod = deps["_uuid"]
        pdf_store = deps["_pdf_store"]

        _uid = await get_user_id_from_token(request)
        exigir_cupo(request, _uid)
        exigir_sesion(request, _uid)
        import httpx

        # Collect all image URLs
        fotos = p.get("property_images") or []
        urls = list(set(filter(None, [f.get("url") or f.get("original") for f in fotos])))

        # Download all images concurrently and convert to base64
        images_b64 = {}
        async with httpx.AsyncClient(timeout=30) as client:
            async def fetch_img(url):
                try:
                    r = await client.get(url, follow_redirects=True, timeout=10.0)
                    if r.status_code == 200:
                        ext = url.split(".")[-1].split("?")[0].lower()
                        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                                "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
                        b64 = base64_mod.b64encode(r.content).decode()
                        images_b64[url] = f"data:{mime};base64,{b64}"
                except Exception:
                    pass  # skip failed images, show blank

            # Limit to 19 gallery images (1 hero + 18 gallery = 3 full pages max)
            await asyncio_mod.gather(*[fetch_img(u) for u in urls[:19]])

        # Build HTML
        html = build_ficha_html(p, images_b64)

        # Render to PDF with Playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = await browser.new_page()
            # Use domcontentloaded instead of networkidle — images are already base64
            await page.set_content(html, wait_until="domcontentloaded")
            await page.wait_for_timeout(500)  # small wait for fonts
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}
            )
            await browser.close()

        from fastapi.responses import JSONResponse
        import re as _re2
        id_prop   = p.get("public_id") or p.get("id") or ""
        loc       = p.get("location") or {}
        colonia   = (loc.get("name") or "").strip()
        tipo_raw  = (p.get("property_type") or "Propiedad").strip()
        # Sanitize: remove accents and special chars for filename
        def _slug(s):
            for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ü','u'),('ñ','n'),
                         ('Á','A'),('É','E'),('Í','I'),('Ó','O'),('Ú','U'),('Ñ','N')]:
                s = s.replace(a, b)
            return _re2.sub(r'[^A-Za-z0-9_]', '_', s).strip('_')
        parts = ["Ficha"]
        if colonia:  parts.append(_slug(colonia))
        filename = "_".join(parts) + ".pdf"
        token = str(uuid_mod.uuid4()).replace("-","")[:16]
        pdf_store[token] = (pdf_bytes, filename)
        # Clean old entries if too many
        if len(pdf_store) > 50:
            oldest = list(pdf_store.keys())[0]
            del pdf_store[oldest]
        return JSONResponse({"token": token, "filename": filename})

    return router
