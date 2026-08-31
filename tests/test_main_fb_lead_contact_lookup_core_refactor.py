"""Permanent guards for Lead Ads contact lookup/patch behavior in Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "facebook_leadgen_processor.py"


class MainFbLeadContactLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CORE.read_text(encoding="utf-8")

    def test_contact_lookup_patch_and_create_all_use_core_database(self):
        source = self.source
        self.assertNotIn("/rest/v1/contactos", source)
        self.assertIn('existing_rows = await get_rows("contactos", filters, timeout=15)', source)
        self.assertIn('await patch_rows(\n                        "contactos",', source)
        self.assertIn('await post_rows(\n                    "contactos",', source)
        self.assertIn('accepted_statuses=(200, 201, 204)', source)

    def test_lookup_patch_and_create_error_contracts_are_preserved(self):
        source = self.source
        self.assertIn("except httpx.HTTPStatusError:\n                existing_rows = []", source)
        self.assertIn("existing = existing_rows[0] if existing_rows else None", source)
        self.assertIn('{"id": f"eq.{existing[\'id\']}"}', source)
        self.assertIn('{"es_potencial": True, "updated_at": now}', source)
        self.assertIn('except httpx.HTTPStatusError:\n                    pass', source)
        self.assertIn('except httpx.HTTPStatusError as exc:', source)
        self.assertIn("(exc.response.text or '')[:200]", source)
        self.assertIn('f"Error guardando el contacto: {exc}"', source)
        compile(source, "core/facebook_leadgen_processor.py", "exec")


if __name__ == "__main__":
    unittest.main()
