"""Permanent guards for the CRM read in /facebook/audiences/from-contacts."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainFbAudienceContactsReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/facebook/audiences/from-contacts")')
        end = cls.source.index("\n\nclass FbLookalikeRequest", start)
        cls.block = cls.source[start:end]

    def test_contact_read_has_no_direct_supabase_rest(self):
        self.assertNotIn("/rest/v1/contactos", self.block)

    def test_core_read_preserves_http_contract_and_meta_work(self):
        block = self.block
        self.assertIn('contactos = await get_rows(\n            "contactos",', block)
        self.assertIn("filtros,\n            timeout=30", block)
        self.assertIn("except httpx.HTTPStatusError:", block)
        self.assertIn('raise HTTPException(status_code=502, detail="No se pudieron leer tus contactos.")', block)
        self.assertNotIn("except Exception", block[:block.index("etiquetas_filtro")])
        self.assertIn('r_aud = await _fb_request(', block)
        self.assertIn('await _fb_guardar_audiencia(user_id, org_id, {', block)
        self.assertIn('await _fb_request(client, "DELETE", audience_id', block)


if __name__ == "__main__":
    unittest.main()
