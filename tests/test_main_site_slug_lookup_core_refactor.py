"""Permanent guards for public site slug usuarios lookup through Core."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainSiteSlugLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_main_compiles(self):
        compile(self.source, "main.py", "exec")

    def test_slug_lookup_preserves_http_empty_404_and_lead_writes(self):
        start = self.source.index('@app.post("/sitio/{slug}/lead")')
        block = self.source[start:]

        self.assertIn('rows = await get_rows(\n                "usuarios",', block)
        self.assertIn('"slug": f"eq.{slug}"', block)
        self.assertIn('"sitio_activo": "eq.true"', block)
        self.assertIn('"select": "id"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError:\n            rows = []", block)
        self.assertIn('raise HTTPException(status_code=404, detail="Sitio no encontrado")', block)
        self.assertIn('user_id = rows[0]["id"]', block)
        lookup = block.split("# 2) Dedup", 1)[0]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/usuarios", lookup)
        # Contact dedupe/create writes stay in the legacy client for this read-only cut.
        self.assertIn("/rest/v1/contactos", block)


if __name__ == "__main__":
    unittest.main()
