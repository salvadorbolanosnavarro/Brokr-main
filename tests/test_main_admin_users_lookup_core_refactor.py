"""Permanent guards for admin_list_users' usuarios read through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "admin_read.py"


class MainAdminUsersLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_admin_users_lookup_uses_core_and_preserves_http_error_detail(self):
        block = self.block
        self.assertIn('users = await get_rows(\n            "usuarios",', block)
        self.assertIn('"select": "id,email,nombre,telefono,rol,activo,created_at"', block)
        self.assertIn('"order": "created_at.desc"', block)
        self.assertIn('"limit": "10000"', block)
        self.assertIn("timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError as exc:", block)
        self.assertIn('raise HTTPException(status_code=500, detail=f"Error listando usuarios: {exc.response.text}")', block)

    def test_admin_users_lookup_does_not_broaden_scope(self):
        block = self.block
        lookup = block.split("try:\n        subs = await get_rows(", 1)[0]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/usuarios", lookup)
        self.assertIn('subs = await get_rows(\n            "suscripciones",', block)
        self.assertNotIn("/rest/v1/suscripciones", block)


if __name__ == "__main__":
    unittest.main()
