"""Permanent guard for Facebook Lead Ads contact creation through Core."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainFbLeadContactPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index("async def _fb_procesar_lead(valor: dict) -> None:")
        end = cls.source.index('\n\n@app.post("/facebook/leadgen/subscribe")', start)
        cls.block = cls.source[start:end]

    def test_contact_creation_delegates_to_core(self):
        block = self.block
        self.assertIn('await post_rows(\n                    "contactos",', block)
        self.assertIn('{k: v for k, v in contacto.items() if v not in ("", None, [])}', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=15', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/contactos"', block)

    def test_http_and_transport_error_contract_stays_intact(self):
        block = self.block
        self.assertIn('except httpx.HTTPStatusError as e:', block)
        self.assertIn("(e.response.text or '')[:200]", block)
        self.assertIn('No se pudo crear el contacto:', block)
        self.assertIn('except Exception as e:', block)
        self.assertIn('await _anota({"error_detail": f"Error guardando el contacto: {e}"})', block)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
