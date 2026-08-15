"""Dry-run the narrow main.py auth migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_main_auth import transform

ROOT = Path(__file__).resolve().parents[1]


class MainAuthRefactorTests(unittest.TestCase):
    def test_transform_routes_shared_user_id_auth_through_core_and_compiles(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.auth import get_user_id_from_token", updated)
        self.assertNotIn("async def get_user_id_from_token", updated)
        # Two endpoint-specific user-email lookups still call Supabase Auth
        # directly; they are a separate migration cut and must not be hidden.
        self.assertEqual(updated.count('/auth/v1/user'), 2)
        # Existing callers keep the same non-raising Optional[str] contract.
        self.assertIn("await get_user_id_from_token(request)", updated)
        # Broad env/database migration remains a later cut.
        self.assertIn('EB_API_KEY       = os.environ.get("EB_API_KEY", "")', updated)
        compile(updated, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
