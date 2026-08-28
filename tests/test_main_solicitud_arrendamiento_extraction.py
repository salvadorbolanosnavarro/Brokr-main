from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "solicitud_arrendamiento.py"


class SolicitudArrendamientoExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.legacy_owned = '@app.post("/solicitud-arrendamiento/analizar")' in cls.main
        cls.owner = cls.main if cls.legacy_owned else cls.router

    def test_auth_and_upload_limits_are_preserved(self):
        o = self.owner
        self.assertIn('user_id = await get_user_id_from_token(request)', o)
        self.assertIn('status_code=401, detail="Inicia sesión para usar este módulo."', o)
        self.assertIn('status_code=500, detail="ANTHROPIC_API_KEY no configurada en el servidor."', o)
        self.assertIn('if len(content) > 15 * 1024 * 1024:', o)
        self.assertIn('status_code=413, detail="Archivo demasiado grande (máx 15 MB)."', o)
        self.assertIn('if len(content) < 100:', o)
        self.assertIn('status_code=400, detail="Archivo vacío o corrupto."', o)
        self.assertIn('docs_validos = (documentos or [])[:5]', o)
        self.assertIn('max_bytes: int = 8 * 1024 * 1024', o)

    def test_document_format_contract_is_preserved(self):
        o = self.owner
        self.assertIn('is_pdf = ctype == "application/pdf" or fname.endswith(".pdf")', o)
        self.assertIn('is_docx = "wordprocessingml" in ctype or fname.endswith(".docx")', o)
        self.assertIn('[".jpg", ".jpeg", ".png", ".webp", ".gif"]', o)
        self.assertIn('"\\n".join(_parts)[:10000]', o)
        self.assertIn('"\\n".join(parts)[:18000]', o)
        self.assertIn('detail="El DOCX no contiene texto legible."', o)
        self.assertIn('detail="Formato no soportado. Sube PDF, imagen (JPG/PNG/WEBP) o DOCX."', o)

    def test_claude_and_telemetry_contract_is_preserved(self):
        o = self.owner
        self.assertIn('httpx.AsyncClient(timeout=150)', o)
        self.assertIn('f"{ANTHROPIC_BASE}/messages"', o)
        self.assertIn('"anthropic-version": "2023-06-01"', o)
        self.assertIn('"model": "claude-sonnet-4-6"', o)
        self.assertIn('"max_tokens": 4096', o)
        self.assertIn('_track_anthropic(user_id, "solicitud-arr", "/solicitud-arrendamiento/analizar",', o)
        self.assertIn('status_code=502, detail="Claude devolvió respuesta vacía."', o)
        self.assertIn('except httpx.TimeoutException:', o)
        self.assertIn('status_code=504, detail="El análisis tardó demasiado. Intenta de nuevo."', o)

    def test_json_extraction_and_defaults_are_preserved(self):
        o = self.owner
        self.assertIn("re.search(r'<output>\\s*(.*?)\\s*</output>', reply_text, re.DOTALL | re.IGNORECASE)", o)
        self.assertIn("re.search(r'\\{.*\\}', reply_text, re.DOTALL)", o)
        self.assertIn('detail="Claude no devolvió JSON válido."', o)
        self.assertIn('if "puntaje" not in parsed or "nivel_riesgo" not in parsed:', o)
        self.assertIn('parsed.setdefault("datos_extraidos", {})', o)
        self.assertIn('parsed.setdefault("secciones", [])', o)
        self.assertIn('parsed.setdefault("banderas_rojas", [])', o)
        self.assertIn('parsed.setdefault("recomendaciones", [])', o)
        self.assertIn('parsed.setdefault("veredicto_corto", "")', o)

    def test_ownership_is_transitional_and_factory_is_prepared(self):
        self.assertIn('@router.post("/solicitud-arrendamiento/analizar")', self.router)
        self.assertIn('def create_router(get_context):', self.router)
        if self.legacy_owned:
            self.assertNotIn('create_solicitud_arrendamiento_router', self.main)
        else:
            self.assertNotIn('@app.post("/solicitud-arrendamiento/analizar")', self.main)
            self.assertIn('from routers.solicitud_arrendamiento import create_router as create_solicitud_arrendamiento_router', self.main)
            self.assertIn('app.include_router(create_solicitud_arrendamiento_router(lambda: {', self.main)
            for seam in (
                '"get_user_id_from_token": get_user_id_from_token',
                '"HTTPException": HTTPException',
                '"ANTHROPIC_API_KEY": ANTHROPIC_API_KEY',
                '"ANTHROPIC_BASE": ANTHROPIC_BASE',
                '"_track_anthropic": _track_anthropic',
                '"httpx": httpx',
                '"base64": base64',
                '"io": io',
                '"re": re',
                '"json": json',
            ):
                self.assertIn(seam, self.main)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/solicitud_arrendamiento.py", "exec")


if __name__ == "__main__":
    unittest.main()
