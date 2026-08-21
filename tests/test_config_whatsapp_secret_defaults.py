from pathlib import Path
import unittest

from scripts.refactor_config_remove_whatsapp_secret_defaults import transform_source

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "core" / "config.py"


class WhatsAppSecretDefaultTests(unittest.TestCase):
    def test_transform_removes_known_public_operational_defaults(self):
        source = CONFIG.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertNotIn('"123456"', transformed)
        self.assertNotIn('"broquer2_verify"', transformed)
        self.assertNotIn('"142857"', transformed)
        self.assertIn('wa_register_pin=os.getenv("WA_REGISTER_PIN", "").strip()', transformed)
        self.assertIn('wa2_verify_token=os.getenv("WA2_VERIFY_TOKEN", "").strip()', transformed)
        self.assertIn('wa2_register_pin=os.getenv("WA_REGISTER_PIN", "").strip()', transformed)
        compile(transformed, "core/config.py", "exec")

    def test_transform_is_idempotent(self):
        source = CONFIG.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
