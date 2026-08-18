"""Permanent guards for admin role/active writes through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainAdminUserPatchesCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, start_marker: str, end_marker: str) -> str:
        start = self.source.index(start_marker)
        end = self.source.index(end_marker, start)
        return self.source[start:end]

    def test_role_patch_preserves_exact_status_and_error_text(self):
        block = self._block('@app.post("/admin/user/rol")', '\n\nclass AdminActivoReq')
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
        block = self._block('@app.post("/admin/user/activo")', '\n\nclass AdminEliminarReq')
        self.assertIn('if target_id == caller_id and not req.activo:', block)
        self.assertIn('await patch_rows_no_response(', block)
        self.assertIn('{"activo": bool(req.activo)}', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('except httpx.HTTPStatusError as exc:', block)
        self.assertIn('detail=f"Error actualizando activo: {exc.response.text}"', block)
        self.assertNotIn('/rest/v1/usuarios', block)


if __name__ == "__main__":
    unittest.main()
