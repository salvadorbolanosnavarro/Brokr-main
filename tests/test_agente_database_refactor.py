"""Dry-run Agente database migration while protecting the agent behavior."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_agente_database import transform

ROOT = Path(__file__).resolve().parents[1]


class AgenteDatabaseRefactorTests(unittest.TestCase):
    def test_transform_routes_supabase_through_core_and_compiles(self):
        source = (ROOT / "routers" / "agente.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.database import get_rows, patch_rows, post_rows", updated)
        self.assertIn("class _CoreDbClient:", updated)
        self.assertNotIn("def _sb_headers()", updated)
        self.assertNotIn("SUPABASE_SERVICE_KEY =", updated)
        self.assertNotIn("headers=_sb_headers()", updated)
        self.assertNotIn("async with httpx.AsyncClient(timeout=15) as client:", updated)
        self.assertIn("async with httpx.AsyncClient(timeout=90) as client:", updated)
        self.assertIn("async with httpx.AsyncClient(timeout=60) as client:", updated)
        self.assertIn("https://api.anthropic.com/v1", updated)
        self.assertIn("https://api.groq.com/openai/v1", updated)
        self.assertIn("SERVER_TOOLS = {", updated)
        self.assertIn("def _build_system(", updated)
        self.assertIn("def _to_client_action(", updated)
        compile(updated, "routers/agente.py", "exec")


if __name__ == "__main__":
    unittest.main()
