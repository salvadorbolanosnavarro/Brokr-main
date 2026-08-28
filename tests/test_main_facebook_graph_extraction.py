"""Permanent guards for the shared Meta Graph transport living in Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
GRAPH = ROOT / "core" / "facebook_graph.py"
CAMPAIGN_TOGGLE = ROOT / "routers" / "facebook_campaign_toggle.py"
QA_SELFCHECK = ROOT / "routers" / "facebook_qa_selfcheck.py"


class FacebookGraphExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.graph = GRAPH.read_text(encoding="utf-8")
        cls.campaign_toggle = CAMPAIGN_TOGGLE.read_text(encoding="utf-8")
        cls.qa_selfcheck = QA_SELFCHECK.read_text(encoding="utf-8")

    def test_consumers_delegate_graph_transport_to_core(self):
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
            "_fb_batch",
        ):
            self.assertNotIn(f"def {name}(", self.main)
            self.assertNotIn(f"async def {name}(", self.main)

        route_in_main = '@app.post("/facebook/qa-selfcheck")' in self.main
        if route_in_main:
            self.assertIn("await _fb_paginate(", self.main)
            self.assertIn("await _fb_request(", self.main)
        else:
            self.assertNotIn("_fb_paginate,", self.main)
            self.assertNotIn("_fb_request,", self.main)
            self.assertIn("await _fb_paginate(", self.qa_selfcheck)
            self.assertIn("await _fb_request(", self.qa_selfcheck)

        self.assertIn("await _fb_batch(", self.campaign_toggle)

    def test_core_preserves_retry_token_pagination_and_batch_policy(self):
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
        self.assertIn("async def _fb_batch(", graph)
        self.assertIn("for i in range(0, len(peticiones), 50):", graph)
        self.assertIn('data={"batch": json.dumps(lote), "include_headers": "false"}', graph)
        self.assertIn('{"code": 0, "body": "Respuesta ilegible de Facebook"}', graph)
        self.assertIn('{"code": 0, "body": "Respuesta inesperada de Facebook"}', graph)
        self.assertIn('{"code": 0, "body": "Elemento inesperado"}', graph)

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
        compile(self.campaign_toggle, "routers/facebook_campaign_toggle.py", "exec")
        compile(self.qa_selfcheck, "routers/facebook_qa_selfcheck.py", "exec")


if __name__ == "__main__":
    unittest.main()
