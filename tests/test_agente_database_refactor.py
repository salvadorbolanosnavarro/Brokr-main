"""Permanent regression guard for Agente database migration."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AgenteDatabaseRegressionTests(unittest.TestCase):
    def test_router_routes_supabase_through_core_and_keeps_ai_clients(self):
        source = (ROOT / "routers" / "agente.py").read_text(encoding="utf-8")

        self.assertIn("from core.database import get_rows, patch_rows, post_rows", source)
        self.assertIn("class _CoreDbClient:", source)
        self.assertNotIn("def _sb_headers()", source)
        self.assertNotIn("SUPABASE_SERVICE_KEY =", source)
        self.assertNotIn("headers=_sb_headers()", source)
        self.assertNotIn("async with httpx.AsyncClient(timeout=15) as client:", source)
        self.assertIn("async with httpx.AsyncClient(timeout=90) as client:", source)
        self.assertIn("async with httpx.AsyncClient(timeout=60) as client:", source)
        self.assertIn("https://api.anthropic.com/v1", source)
        self.assertIn("https://api.groq.com/openai/v1", source)
        self.assertIn("SERVER_TOOLS = {", source)
        self.assertIn("def _build_system(", source)
        self.assertIn("def _to_client_action(", source)
        compile(source, "routers/agente.py", "exec")


if __name__ == "__main__":
    unittest.main()
