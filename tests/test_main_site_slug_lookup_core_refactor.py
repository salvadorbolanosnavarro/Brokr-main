"""Permanent guards for public site lead database routing through Core."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "public_site_leads.py"
MAIN = ROOT / "main.py"


class MainSiteSlugLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")
        cls.main_source = MAIN.read_text(encoding="utf-8")

    def test_router_and_main_compile(self):
        compile(self.source, "routers/public_site_leads.py", "exec")
        compile(self.main_source, "main.py", "exec")

    def test_site_lead_database_flow_uses_core_and_preserves_contracts(self):
        start = self.source.index('@router.post("/sitio/{slug}/lead")')
        block = self.source[start:]

        self.assertIn('rows = await get_rows(', block)
        self.assertIn('"usuarios"', block)
        self.assertIn('"slug": f"eq.{slug}"', block)
        self.assertIn('"sitio_activo": "eq.true"', block)
        self.assertIn('raise HTTPException(status_code=404, detail="Sitio no encontrado")', block)
        self.assertIn('filas = await get_rows(', block)
        self.assertIn('await patch_rows(', block)
        self.assertIn('await post_rows(', block)
        self.assertIn('accepted_statuses=(200, 201)', block)
        self.assertIn('raise HTTPException(status_code=502, detail="No se pudo registrar el lead")', block)
        self.assertNotIn('/rest/v1/usuarios', block)
        self.assertNotIn('/rest/v1/contactos', block)

    def test_router_is_mounted_once_and_legacy_route_removed(self):
        self.assertEqual(
            self.main_source.count(
                'from routers.public_site_leads import router as public_site_leads_router'
            ),
            1,
        )
        self.assertEqual(self.main_source.count('app.include_router(public_site_leads_router)'), 1)
        self.assertNotIn('@app.post("/sitio/{slug}/lead")', self.main_source)


if __name__ == "__main__":
    unittest.main()
