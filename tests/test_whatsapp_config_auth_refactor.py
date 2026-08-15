"""Permanent regression guard for WhatsApp 2 config/auth migration."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WhatsAppConfigAuthRegressionTests(unittest.TestCase):
    def test_router_uses_core_config_and_auth(self):
        source = (ROOT / "whatsapp.py").read_text(encoding="utf-8")

        self.assertIn("from core.auth import require_user_id", source)
        self.assertIn("from core.config import settings", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("async def get_user_id_from_token", source)
        self.assertNotIn("or SUPABASE_ANON_KEY", source)
        self.assertIn("SUPABASE_SERVICE_KEY = settings.supabase_service_key", source)
        self.assertIn("WA2_MODEL         = settings.wa2_model", source)
        self.assertIn("META_APP_ID     = settings.wa2_meta_app_id", source)
        self.assertIn("WA2_VERIFY_TOKEN = settings.wa2_verify_token", source)
        self.assertIn("WA2_APP_SECRET   = settings.wa2_app_secret", source)
        self.assertIn("WA2_DEBOUNCE = settings.wa2_debounce_seconds", source)
        self.assertIn("WA2_CAMPANA_TOPE = settings.wa2_campaign_limit", source)
        self.assertIn("WA2_TOPE_IA = settings.wa2_ai_limit", source)
        self.assertIn('return await require_user_id(request, detail="No autorizado")', source)
        # Database helpers remain a separate migration cut.
        self.assertIn("def _sb_headers() -> dict:", source)
        self.assertIn("async def sb_get(", source)
        compile(source, "whatsapp.py", "exec")


if __name__ == "__main__":
    unittest.main()
