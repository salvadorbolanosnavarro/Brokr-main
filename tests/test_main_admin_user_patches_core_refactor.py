"""Permanent guards for admin role/active writes through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "admin_accounts.py"


class MainAdminUserPatchesCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")

    def test_role_patch_preserves_exact_status_and_error_text(self):
        block = self.source
        self.assertIn('await patch_rows_no_response(', block)
        self.assertIn('"usuarios"', block)
        self.assertIn('{"id": f"eq.{target_id}"}', block)
        self.assertIn('{"rol": req.rol}', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('timeout=10', block)
        self.assertIn('except httpx.HTTPStatusError as exc:', block)
        self.assertIn('detail=f"Error actualizando rol: {exc.response.text}"', block)
        self.assertNotIn('/rest/v1/usuarios', block)

    def test_active_patch_preserves_exact_status_and_self_protection(self):
        block = self.source
        self.assertIn('if target_id == caller_id and not req.activo:', block)
        self.assertIn('await patch_rows_no_response(', block)
        self.assertIn('{"activo": bool(req.activo)}', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('except httpx.HTTPStatusError as exc:', block)
        self.assertIn('detail=f"Error actualizando activo: {exc.response.text}"', block)
        self.assertNotIn('/rest/v1/usuarios', block)


if __name__ == "__main__":
    unittest.main()
