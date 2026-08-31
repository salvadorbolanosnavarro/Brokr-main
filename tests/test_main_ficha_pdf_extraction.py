from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "ficha_pdf.py"


class FichaPdfExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.legacy_owned = '@app.post("/ficha-pdf")' in cls.main
        cls.owner = cls.main if cls.legacy_owned else cls.router

    def test_auth_and_session_contract_are_preserved(self):
        owner = self.owner
        if self.legacy_owned:
            self.assertIn('_uid = await get_user_id_from_token(request)', owner)
            self.assertIn('exigir_cupo(request, _uid)', owner)
            self.assertIn('exigir_sesion(request, _uid)', owner)
        else:
            self.assertIn('_uid = await get_user_id_from_token(request)', owner)
            self.assertIn('exigir_cupo(request, _uid)', owner)
            self.assertIn('exigir_sesion(request, _uid)', owner)
            self.assertIn('"get_user_id_from_token": get_user_id_from_token', self.main)
            self.assertIn('"exigir_cupo": exigir_cupo', self.main)
            self.assertIn('"exigir_sesion": exigir_sesion', self.main)

    def test_image_download_and_render_contract_are_preserved(self):
        owner = self.owner
        self.assertIn('fotos = p.get("property_images") or []', owner)
        self.assertIn('urls[:19]', owner)
        self.assertIn('follow_redirects=True, timeout=10.0', owner)
        self.assertIn('timeout=30', owner)
        self.assertIn('launch(args=["--no-sandbox", "--disable-dev-shm-usage"])', owner)
        self.assertIn('set_content(html, wait_until="domcontentloaded")', owner)
        self.assertIn('wait_for_timeout(500)', owner)
        self.assertIn('format="A4"', owner)
        self.assertIn('print_background=True', owner)
        self.assertIn('margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}', owner)

    def test_filename_store_and_eviction_contract_are_preserved(self):
        owner = self.owner
        self.assertIn('parts = ["Ficha"]', owner)
        self.assertIn('filename = "_".join(parts) + ".pdf"', owner)
        self.assertIn('return JSONResponse({"token": token, "filename": filename})', owner)
        if self.legacy_owned:
            self.assertIn('token = str(_uuid.uuid4()).replace("-","")[:16]', owner)
            self.assertIn('_pdf_store[token] = (pdf_bytes, filename)', owner)
            self.assertIn('if len(_pdf_store) > 50:', owner)
        else:
            self.assertIn('token = str(uuid_mod.uuid4()).replace("-","")[:16]', owner)
            self.assertIn('pdf_store[token] = (pdf_bytes, filename)', owner)
            self.assertIn('if len(pdf_store) > 50:', owner)

    def test_ownership_is_transitional_and_factory_is_prepared(self):
        self.assertIn('@router.post("/ficha-pdf")', self.router)
        self.assertIn('def create_router(get_context):', self.router)
        if self.legacy_owned:
            self.assertNotIn('create_ficha_pdf_router', self.main)
        else:
            self.assertNotIn('@app.post("/ficha-pdf")', self.main)
            self.assertIn('from routers.ficha_pdf import create_router as create_ficha_pdf_router', self.main)
            self.assertIn('app.include_router(create_ficha_pdf_router(lambda: {', self.main)
            for seam in (
                '"get_user_id_from_token": get_user_id_from_token',
                '"exigir_cupo": exigir_cupo',
                '"exigir_sesion": exigir_sesion',
                '"base64": base64',
                '"asyncio": asyncio',
                '"build_ficha_html": build_ficha_html',
                '"async_playwright": async_playwright',
                '"_uuid": _uuid',
                '"_pdf_store": _pdf_store',
            ):
                self.assertIn(seam, self.main)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/ficha_pdf.py", "exec")


if __name__ == "__main__":
    unittest.main()
