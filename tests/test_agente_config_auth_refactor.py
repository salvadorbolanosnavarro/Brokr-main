"""Permanent regression guard for Agente config/auth migration."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AgenteConfigAuthRegressionTests(unittest.TestCase):
    def test_router_uses_core_config_and_auth(self):
        source = (ROOT / "routers" / "agente.py").read_text(encoding="utf-8")

        self.assertIn("from core.auth import get_user_id_from_token", source)
        self.assertIn("from core.config import settings", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("async def _get_user_id", source)
        self.assertNotIn("SUPABASE_SERVICE_KEY = os.environ", source)
        self.assertNotIn("or SUPABASE_KEY", source)
        self.assertIn("ANTHROPIC_API_KEY    = settings.anthropic_api_key", source)
        self.assertIn("GROQ_API_KEY         = settings.groq_api_key", source)
        self.assertIn("SUPABASE_SERVICE_KEY = settings.supabase_service_key", source)
        # Direct DB access remains a separate migration cut for now.
        self.assertIn("def _sb_headers() -> dict:", source)
        self.assertIn("https://api.anthropic.com/v1", source)
        self.assertIn("https://api.groq.com/openai/v1", source)
        compile(source, "routers/agente.py", "exec")


if __name__ == "__main__":
    unittest.main()
