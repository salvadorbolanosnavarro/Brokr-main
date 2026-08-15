"""Dry-run the narrow main.py auth migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_main_auth import transform

ROOT = Path(__file__).resolve().parents[1]


class MainAuthRefactorTests(unittest.TestCase):
    def test_transform_routes_auth_through_core_and_compiles(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.auth import get_user_id_from_token", updated)
        self.assertNotIn("async def get_user_id_from_token", updated)
        self.assertNotIn('/auth/v1/user', updated)
        # Existing callers keep the same non-raising Optional[str] contract.
        self.assertIn("await get_user_id_from_token(request)", updated)
        # Broad env/database migration remains a later cut.
        self.assertIn('EB_API_KEY       = os.environ.get("EB_API_KEY", "")', updated)
        compile(updated, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
