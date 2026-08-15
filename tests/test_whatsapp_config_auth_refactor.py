"""Dry-run WhatsApp 2 config/auth migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_whatsapp_config_auth import transform

ROOT = Path(__file__).resolve().parents[1]


class WhatsAppConfigAuthRefactorTests(unittest.TestCase):
    def test_transform_uses_core_config_and_auth_and_compiles(self):
        source = (ROOT / "whatsapp.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.auth import require_user_id", updated)
        self.assertIn("from core.config import settings", updated)
        self.assertNotIn("os.environ", updated)
        self.assertNotIn("async def get_user_id_from_token", updated)
        self.assertNotIn("or SUPABASE_ANON_KEY", updated)
        self.assertIn("SUPABASE_SERVICE_KEY = settings.supabase_service_key", updated)
        self.assertIn("WA2_MODEL         = settings.wa2_model", updated)
        self.assertIn("META_APP_ID     = settings.wa2_meta_app_id", updated)
        self.assertIn("WA2_VERIFY_TOKEN = settings.wa2_verify_token", updated)
        self.assertIn("WA2_APP_SECRET   = settings.wa2_app_secret", updated)
        self.assertIn("WA2_DEBOUNCE = settings.wa2_debounce_seconds", updated)
        self.assertIn("WA2_CAMPANA_TOPE = settings.wa2_campaign_limit", updated)
        self.assertIn("WA2_TOPE_IA = settings.wa2_ai_limit", updated)
        self.assertIn('return await require_user_id(request, detail="No autorizado")', updated)
        # Database helpers are deliberately the next isolated cut.
        self.assertIn("def _sb_headers() -> dict:", updated)
        self.assertIn("async def sb_get(", updated)
        compile(updated, "whatsapp.py", "exec")


if __name__ == "__main__":
    unittest.main()
