from pathlib import Path
import unittest

from scripts.refactor_main_avm_websearch_ssrf_core import transform_source as ssrf_transform
from scripts.refactor_main_extract_avm_websearch_core import transform_source as extract_transform

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "avm_websearch.py"


class MainAvmWebsearchExtractionTests(unittest.TestCase):
    def test_router_preserves_search_fetch_ai_and_fallback_contracts(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            '@router.post("/api/avm-websearch")',
            '"https://www.googleapis.com/customsearch/v1"',
            '"https://serpapi.com/search.json"',
            '"https://api.search.brave.com/res/v1/web/search"',
            '"https://api.tavily.com/search"',
            '"https://api.firecrawl.dev/v1/scrape"',
            '"proxy": "auto"',
            "await fetch_public_http_result(",
            'status in (403, 429) or status >= 500',
            '"max_tokens": 8000',
            '"temperature": 0.05',
            '"avm",\n        "/api/avm-websearch"',
            'resultado["valor_minimo"]',
            'resultado["valor_maximo"]',
            'resultado["fuentes_consultadas"]',
            'resultado["queries_utilizadas"]',
        ):
            self.assertIn(required, source)
        self.assertNotIn("follow_redirects=True, headers=headers", source[source.index("async def _fetch_candidate_pages"):])

    def test_ssrf_then_full_extraction_composes_and_keeps_pdf(self):
        source = MAIN.read_text(encoding="utf-8")
        hardened = ssrf_transform(source)
        transformed = extract_transform(hardened)
        self.assertNotIn('@app.post("/api/avm-websearch")', transformed)
        self.assertNotIn("class AvmWebSearchRequest", transformed)
        self.assertIn("avm_websearch_router", transformed)
        self.assertIn('@app.post("/avm-pdf")', transformed)
        compile(transformed, "main.py", "exec")

    def test_extraction_refuses_unsafe_transport(self):
        with self.assertRaises(RuntimeError):
            extract_transform(MAIN.read_text(encoding="utf-8"))

    def test_extraction_is_idempotent_after_hardening(self):
        once = extract_transform(ssrf_transform(MAIN.read_text(encoding="utf-8")))
        self.assertEqual(once, extract_transform(once))


if __name__ == "__main__":
    unittest.main()
