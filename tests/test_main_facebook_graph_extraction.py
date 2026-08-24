"""Permanent guards for the shared Meta Graph transport living in Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
GRAPH = ROOT / "core" / "facebook_graph.py"


class FacebookGraphExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.graph = GRAPH.read_text(encoding="utf-8")

    def test_main_delegates_graph_transport_to_core(self):
        self.assertIn("from core.facebook_graph import (", self.main)
        for name in (
            "_fb_appsecret_proof",
            "_fb_parse_error",
            "_fb_friendly_error",
            "_fb_espera_por_uso",
            "_fb_debe_reintentar",
            "_fb_request",
            "_fb_exigir_ok",
            "_fb_get_json",
            "_fb_paginate",
        ):
            self.assertNotIn(f"def {name}(", self.main)
            self.assertNotIn(f"async def {name}(", self.main)
        self.assertIn("await _fb_paginate(", self.main)
        self.assertIn("await _fb_request(", self.main)

    def test_core_preserves_retry_token_and_pagination_policy(self):
        graph = self.graph
        self.assertIn('FB_GRAPH = f"https://graph.facebook.com/{FB_API_VERSION}"', graph)
        self.assertIn("_FB_REINTENTOS = 4", graph)
        self.assertIn("_FB_CODIGOS_TOKEN = {102, 190, 463, 467}", graph)
        self.assertIn('r.status_code == 429 or r.status_code >= 500', graph.replace("resp", "r"))
        self.assertIn('r.headers.get("Retry-After")', graph)
        self.assertIn('headers.get("X-Business-Use-Case-Usage")', graph)
        self.assertIn('and "appsecret_proof" in (r.text or "")', graph)
        self.assertIn("await asyncio.sleep", graph)
        self.assertIn("while paginas < max_paginas and len(items) < max_items:", graph)
        self.assertIn("return items[:max_items]", graph)

    def test_core_preserves_business_error_translation(self):
        graph = self.graph
        self.assertIn("_FB_ERRORES_COMUNES", graph)
        self.assertIn("Tu sesión de Facebook expiró", graph)
        self.assertIn("Alcanzaste el límite de peticiones", graph)
        self.assertIn("sc = 401 if code in _FB_CODIGOS_TOKEN else status_code", graph)
        self.assertIn("status_code=504", graph)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.graph, "core/facebook_graph.py", "exec")


if __name__ == "__main__":
    unittest.main()
