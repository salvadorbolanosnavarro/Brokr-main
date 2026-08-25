"""Permanent guard for Facebook Lead Ads contact creation through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "facebook_leadgen_processor.py"


class MainFbLeadContactPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CORE.read_text(encoding="utf-8")

    def test_contact_creation_delegates_to_core_database(self):
        source = self.source
        self.assertIn('await post_rows(\n                    "contactos",', source)
        self.assertIn('{key: val for key, val in contact.items() if val not in ("", None, [])}', source)
        self.assertIn('prefer="return=minimal"', source)
        self.assertIn('timeout=15', source)
        self.assertIn('accepted_statuses=(200, 201, 204)', source)
        self.assertNotIn('/rest/v1/contactos', source)

    def test_http_and_transport_error_contract_stays_intact(self):
        source = self.source
        self.assertIn('except httpx.HTTPStatusError as exc:', source)
        self.assertIn("(exc.response.text or '')[:200]", source)
        self.assertIn('No se pudo crear el contacto:', source)
        self.assertIn('except Exception as exc:', source)
        self.assertIn('f"Error guardando el contacto: {exc}"', source)
        compile(source, "core/facebook_leadgen_processor.py", "exec")


if __name__ == "__main__":
    unittest.main()
