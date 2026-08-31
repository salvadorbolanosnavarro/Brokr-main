"""Permanent regression guard for shared authentication during main.py decomposition."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainAuthRegressionTests(unittest.TestCase):
    def test_main_uses_core_user_id_auth(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        checkout = (ROOT / "routers" / "subscription_checkout.py").read_text(encoding="utf-8")
        enterprise = (ROOT / "routers" / "subscription_enterprise.py").read_text(encoding="utf-8")
        contact_file = (ROOT / "routers" / "contact_file_import.py").read_text(encoding="utf-8")

        self.assertIn("from core.auth import get_user_id_from_token", source)
        self.assertNotIn("async def get_user_id_from_token", source)
        # The two endpoint-specific user-email lookups now live in their
        # subscription routers instead of the bootstrap.
        self.assertEqual(source.count('/auth/v1/user'), 0)
        self.assertEqual(checkout.count('/auth/v1/user'), 1)
        self.assertEqual(enterprise.count('/auth/v1/user'), 1)
        self.assertEqual(
            source.count('/auth/v1/user')
            + checkout.count('/auth/v1/user')
            + enterprise.count('/auth/v1/user'),
            2,
        )
        if '@app.post("/contactos/importar-archivo")' in source:
            self.assertIn("await get_user_id_from_token(request)", source)
        else:
            self.assertIn('"get_user_id_from_token": get_user_id_from_token', source)
            self.assertIn("await get_user_id_from_token(request)", contact_file)
        compile(source, "main.py", "exec")
        compile(checkout, "routers/subscription_checkout.py", "exec")
        compile(enterprise, "routers/subscription_enterprise.py", "exec")
        compile(contact_file, "routers/contact_file_import.py", "exec")


if __name__ == "__main__":
    unittest.main()
