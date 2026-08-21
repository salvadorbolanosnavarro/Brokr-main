from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_webhook_verify_core import transform_source as get_transform
from scripts.refactor_whatsapp_webhook_post_auth_core import transform_source as post_transform

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
AUTH = ROOT / "routers" / "whatsapp_webhook_auth.py"


class WhatsAppWebhookPostAuthTests(unittest.TestCase):
    def test_auth_helper_is_fail_closed_and_constant_time(self):
        source = AUTH.read_text(encoding="utf-8")
        for required in (
            "def meta_signature_error(",
            "if not secret:",
            "Response(status_code=503)",
            '"sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()',
            "hmac.compare_digest(signature or \"\", expected)",
            "Response(status_code=403)",
        ):
            self.assertIn(required, source)

    def test_get_then_post_auth_transforms_compose(self):
        source = TARGET.read_text(encoding="utf-8")
        transformed = post_transform(get_transform(source))
        self.assertIn("auth_error = meta_signature_error(", transformed)
        self.assertNotIn(
            'expected = "sha256=" + hmac.new(WA2_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()',
            transformed,
        )
        self.assertIn("payload = json.loads(raw)", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_post_transform_is_idempotent(self):
        once = post_transform(get_transform(TARGET.read_text(encoding="utf-8")))
        self.assertEqual(once, post_transform(once))


if __name__ == "__main__":
    unittest.main()
