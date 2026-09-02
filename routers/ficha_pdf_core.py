"""Pure PDF generation for the property technical sheet (no auth, no rate
limiting, no HTTP) — shared by the authenticated POST /ficha-pdf endpoint
(routers/ficha_pdf.py) and the WhatsApp receptionist, which calls this
in-process instead of over HTTP so it never needs a live Broquer user
session to act on the connected number's behalf.
"""
from __future__ import annotations

import re as _re

import httpx


async def generar_ficha_pdf_core(
    p: dict, *, base64, asyncio, build_ficha_html, async_playwright, uuid, pdf_store,
) -> tuple[str, str]:
    """Renders the PDF and stores it in pdf_store. Returns (token, filename)."""
    fotos = p.get("property_images") or []
    urls = list(set(filter(None, [f.get("url") or f.get("original") for f in fotos])))

    images_b64: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        async def fetch_img(url):
            try:
                r = await client.get(url, follow_redirects=True, timeout=10.0)
                if r.status_code == 200:
                    ext = url.split(".")[-1].split("?")[0].lower()
                    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
                    b64 = base64.b64encode(r.content).decode()
                    images_b64[url] = f"data:{mime};base64,{b64}"
            except Exception:
                pass  # skip failed images, show blank

        # Limit to 19 gallery images (1 hero + 18 gallery = 3 full pages max)
        await asyncio.gather(*[fetch_img(u) for u in urls[:19]])

    html = build_ficha_html(p, images_b64)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        # Use domcontentloaded instead of networkidle — images are already base64
        await page.set_content(html, wait_until="domcontentloaded")
        await page.wait_for_timeout(500)  # small wait for fonts
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        await browser.close()

    loc = p.get("location") or {}
    colonia = (loc.get("name") or "").strip()

    # Sanitize: remove accents and special chars for filename
    def _slug(s):
        for a, b in [('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ü', 'u'), ('ñ', 'n'),
                     ('Á', 'A'), ('É', 'E'), ('Í', 'I'), ('Ó', 'O'), ('Ú', 'U'), ('Ñ', 'N')]:
            s = s.replace(a, b)
        return _re.sub(r'[^A-Za-z0-9_]', '_', s).strip('_')

    parts = ["Ficha"]
    if colonia:
        parts.append(_slug(colonia))
    filename = "_".join(parts) + ".pdf"

    token = str(uuid.uuid4()).replace("-","")[:16]
    pdf_store[token] = (pdf_bytes, filename)
    # Clean old entries if too many
    if len(pdf_store) > 50:
        oldest = list(pdf_store.keys())[0]
        del pdf_store[oldest]

    return token, filename
