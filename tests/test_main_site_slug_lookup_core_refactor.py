"""Permanent guards for public site lead database routing through Core."""
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

    def test_site_lead_database_flow_uses_core_and_preserves_contracts(self):
        start = self.source.index('@app.post("/sitio/{slug}/lead")')
        block = self.source[start:]

        self.assertIn('rows = await get_rows(\n                "usuarios",', block)
        self.assertIn('"slug": f"eq.{slug}"', block)
        self.assertIn('"sitio_activo": "eq.true"', block)
        self.assertIn('raise HTTPException(status_code=404, detail="Sitio no encontrado")', block)
        self.assertIn('filas = await get_rows(\n                    "contactos",', block)
        self.assertIn('await patch_rows(\n                    "contactos",', block)
        self.assertIn('await post_rows(\n                "contactos",', block)
        self.assertIn('accepted_statuses=(200, 201)', block)
        self.assertIn('raise HTTPException(status_code=502, detail="No se pudo registrar el lead")', block)
        self.assertNotIn('/rest/v1/usuarios', block)
        self.assertNotIn('/rest/v1/contactos', block)


if __name__ == "__main__":
    unittest.main()
