from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "avm_pdf.py"


class AvmPdfExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.legacy_owned = '@app.post("/avm-pdf")' in cls.main
        cls.owner = cls.main if cls.legacy_owned else cls.router

    def test_http_and_error_contract_are_preserved(self):
        owner = self.owner
        self.assertIn('resultado = p.get("resultado", {})', owner)
        self.assertIn('agente = p.get("agente", "Agente Broquer")', owner)
        self.assertIn('status_code=400, detail="Resultado vacío"', owner)
        self.assertNotIn('get_user_id_from_token', self._handler_block(owner))
        self.assertNotIn('exigir_cupo', self._handler_block(owner))
        self.assertNotIn('exigir_sesion', self._handler_block(owner))

    def test_pdf_render_contract_is_preserved(self):
        owner = self.owner
        self.assertIn('"--r-xs:4px; --r-sm:8px; --r:14px; --r-lg:28px; --r-pill:999px;"', owner)
        self.assertIn('launch(args=["--no-sandbox", "--disable-dev-shm-usage"])', owner)
        self.assertIn('set_content(html, wait_until="domcontentloaded")', owner)
        self.assertIn('wait_for_timeout(400)', owner)
        self.assertIn('format="A4"', owner)
        self.assertIn('print_background=True', owner)
        self.assertIn('margin={"top": "10mm", "right": "10mm", "bottom": "10mm", "left": "10mm"}', owner)

    def test_filename_store_and_eviction_contract_are_preserved(self):
        owner = self.owner
        if self.legacy_owned:
            self.assertIn('token = str(_uuid.uuid4()).replace("-", "")[:16]', owner)
            self.assertIn('filename = f"Estimacion_Valor_{colonia_slug}_{time.strftime(\'%Y%m%d\')}.pdf"', owner)
            self.assertIn('_pdf_store[token] = (pdf_bytes, filename)', owner)
            self.assertIn('if len(_pdf_store) > 50:', owner)
        else:
            self.assertIn('token = str(uuid_mod.uuid4()).replace("-", "")[:16]', owner)
            self.assertIn('filename = f"Estimacion_Valor_{colonia_slug}_{time_mod.strftime(\'%Y%m%d\')}.pdf"', owner)
            self.assertIn('pdf_store[token] = (pdf_bytes, filename)', owner)
            self.assertIn('if len(pdf_store) > 50:', owner)
        self.assertIn('colonia_slug = resultado.get("colonia", "propiedad").replace(" ", "_")[:20]', owner)
        self.assertIn('return JSONResponse({"token": token, "filename": filename})', owner)

    def test_ownership_is_transitional_and_factory_is_prepared(self):
        self.assertIn('@router.post("/avm-pdf")', self.router)
        self.assertIn('def create_router(get_context):', self.router)
        if self.legacy_owned:
            self.assertNotIn('create_avm_pdf_router', self.main)
        else:
            self.assertNotIn('@app.post("/avm-pdf")', self.main)
            self.assertIn('from routers.avm_pdf import create_router as create_avm_pdf_router', self.main)
            self.assertIn('app.include_router(create_avm_pdf_router(lambda: {', self.main)
            for seam in ('"HTTPException": HTTPException', '"theme_css_for_pdf": theme_css_for_pdf', '"_pdf_store": _pdf_store', '"_uuid": _uuid', '"time": time'):
                self.assertIn(seam, self.main)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/avm_pdf.py", "exec")

    @staticmethod
    def _handler_block(owner: str) -> str:
        marker = 'async def generar_avm_pdf(p: dict):'
        start = owner.index(marker)
        tail = owner[start:]
        if '\n    return router' in tail:
            return tail.split('\n    return router', 1)[0]
        if '\n\n# ────────────────────────────────────────────\n# CONTRATOS' in tail:
            return tail.split('\n\n# ────────────────────────────────────────────\n# CONTRATOS', 1)[0]
        return tail


if __name__ == "__main__":
    unittest.main()
