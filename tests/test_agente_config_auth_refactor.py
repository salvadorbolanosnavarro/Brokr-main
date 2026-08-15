"""Dry-run Agente config/auth migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_agente_config_auth import transform

ROOT = Path(__file__).resolve().parents[1]


class AgenteConfigAuthRefactorTests(unittest.TestCase):
    def test_transform_uses_core_config_and_auth_and_compiles(self):
        source = (ROOT / "routers" / "agente.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.auth import get_user_id_from_token", updated)
        self.assertIn("from core.config import settings", updated)
        self.assertNotIn("os.environ", updated)
        self.assertNotIn("async def _get_user_id", updated)
        self.assertNotIn("SUPABASE_SERVICE_KEY = os.environ", updated)
        self.assertNotIn("or SUPABASE_KEY", updated)
        self.assertIn("ANTHROPIC_API_KEY    = settings.anthropic_api_key", updated)
        self.assertIn("GROQ_API_KEY         = settings.groq_api_key", updated)
        self.assertIn("SUPABASE_SERVICE_KEY = settings.supabase_service_key", updated)
        # Database access and AI clients are intentionally separate cuts.
        self.assertIn("def _sb_headers() -> dict:", updated)
        self.assertIn("https://api.anthropic.com/v1", updated)
        self.assertIn("https://api.groq.com/openai/v1", updated)
        compile(updated, "routers/agente.py", "exec")


if __name__ == "__main__":
    unittest.main()
