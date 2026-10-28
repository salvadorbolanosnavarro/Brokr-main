"""Los endpoints de las acciones de Broquer Max validan la suscripción en el
servidor, no solo con el candado del navegador (app-shell.js)."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GATED = {
    "routers/avm_websearch.py": "user_id = await require_paid_feature_access(request)",
    "routers/contracts_basic.py": "user_id = await require_paid_feature_access(request)",
    "routers/isr_pdf.py": "_uid = await require_paid_feature_access(request)",
    "routers/ficha_pdf.py": "_uid = await require_paid_feature_access(request)",
    "routers/facebook_ad_description.py": "user_id = await require_paid_feature_access(request)",
    "routers/facebook_create_ad.py": "user_id = await require_paid_feature_access(request)",
    "routers/whatsapp_connection.py": "if not await has_paid_feature_access(user_id):",
}


class PremiumEndpointsPaidGateTests(unittest.TestCase):
    def test_premium_endpoints_require_paid_access(self):
        for path, gate in GATED.items():
            with self.subTest(path=path):
                self.assertIn(gate, (ROOT / path).read_text(encoding="utf-8"))

    def test_video_and_image_cleaner_stay_free(self):
        # video.html (libre por decisión de producto) usa /images/clean.
        for path in ("routers/video.py", "routers/image_cleaner.py"):
            with self.subTest(path=path):
                src = (ROOT / path).read_text(encoding="utf-8")
                self.assertNotIn("await require_paid_feature_access(", src)
                self.assertNotIn("await has_paid_feature_access(", src)


if __name__ == "__main__":
    unittest.main()
