from pathlib import Path
import unittest

from routers.whatsapp_identity import es_asesor, solo_digitos
from scripts.refactor_whatsapp_extract_identity_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"


class WhatsAppIdentityExtractionTests(unittest.TestCase):
    def test_phone_identity_contract(self):
        numero = {"numero_personal": "+52 443 123 4567", "phone_number": "5214437654321"}
        self.assertEqual(solo_digitos("+52 (443) 123-4567"), "524431234567")
        self.assertTrue(es_asesor(numero, "5214431234567"))
        self.assertTrue(es_asesor(numero, "524437654321"))
        self.assertFalse(es_asesor(numero, "524431111111"))
        self.assertFalse(es_asesor(numero, "123"))

    def test_transform_reuses_shared_helpers(self):
        source = TARGET.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from routers.whatsapp_identity import", transformed)
        self.assertNotIn("def _solo_digitos(", transformed)
        self.assertNotIn("def _es_asesor(", transformed)
        self.assertIn("async def _agenda_upsert", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
