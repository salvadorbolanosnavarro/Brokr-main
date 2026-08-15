"""Permanent regression guard for main.py shared authentication."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainAuthRegressionTests(unittest.TestCase):
    def test_main_uses_core_user_id_auth(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertIn("from core.auth import get_user_id_from_token", source)
        self.assertNotIn("async def get_user_id_from_token", source)
        # Two endpoint-specific user-email lookups still call Supabase Auth
        # directly; they are a separate migration cut and must not grow.
        self.assertEqual(source.count('/auth/v1/user'), 2)
        self.assertIn("await get_user_id_from_token(request)", source)
        compile(source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
