from pathlib import Path
import unittest

from scripts.refactor_whatsapp_security_defaults_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "core" / "config.py"


class WhatsAppSecurityDefaultsTransformTests(unittest.TestCase):
    def test_transform_removes_public_operational_secret_defaults(self):
        source = CONFIG.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn('wa_register_pin=os.getenv("WA_REGISTER_PIN", "").strip()', transformed)
        self.assertIn('wa2_verify_token=os.getenv("WA2_VERIFY_TOKEN", "").strip()', transformed)
        self.assertIn('wa2_register_pin=os.getenv("WA_REGISTER_PIN", "").strip()', transformed)
        self.assertNotIn('wa_register_pin=os.getenv("WA_REGISTER_PIN", "123456")', transformed)
        self.assertNotIn("broquer2_verify", transformed)
        self.assertNotIn('wa2_register_pin=os.getenv("WA_REGISTER_PIN", "142857")', transformed)
        compile(transformed, "core/config.py", "exec")

    def test_transform_is_idempotent(self):
        source = CONFIG.read_text(encoding="utf-8")
        once = transform_source(source)
        twice = transform_source(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
