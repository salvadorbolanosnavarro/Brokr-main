"""Permanent guards for destructive admin user deletion I/O routed through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "admin_delete.py"


class MainAdminDeleteCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_target_lookup_preserves_exact_200_fail_soft_http_contract(self):
        block = self.block
        self.assertIn('filas = await get_service_json(', block)
        self.assertIn('"usuarios"', block)
        self.assertIn('{"id": f"eq.{target_id}", "select": "id,email,rol", "limit": "1"}', block)
        self.assertIn('accepted_statuses=(200,)', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('filas = []', block)
        self.assertNotIn('/rest/v1/usuarios', block)

    def test_all_safety_guards_remain_before_rpc(self):
        block = self.block
        rpc = block.index('resultado = await call_service_rpc(')
        for text in [
            'caller_id = await require_legacy_admin(request)',
            'if target_id == caller_id:',
            'if (objetivo.get("rol") or "agente") == "admin":',
            'if (req.email_confirmacion or "").strip().lower() != email_real:',
            'rutas_fotos = await _storage_rutas_fotos_de_usuario(target_id)',
        ]:
            self.assertIn(text, block)
            self.assertLess(block.index(text), rpc)

    def test_destructive_rpc_uses_service_core_with_exact_status_and_result_check(self):
        block = self.block
        self.assertIn('resultado = await call_service_rpc(', block)
        self.assertIn('"admin_eliminar_usuario_total"', block)
        self.assertIn('{"p_user_id": target_id}', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200,)', block)
        self.assertIn('except httpx.HTTPStatusError as exc:', block)
        self.assertIn('detail=f"Error eliminando usuario: {exc.response.text}"', block)
        self.assertIn('if not (isinstance(resultado, dict) and resultado.get("ok")):', block)
        self.assertNotIn('/rest/v1/rpc/admin_eliminar_usuario_total', block)

    def test_storage_cleanup_still_occurs_only_after_rpc_success(self):
        block = self.block
        self.assertLess(block.index('if not (isinstance(resultado, dict)'), block.index('archivos_borrados = await _storage_borrar_carpeta_usuario'))


if __name__ == "__main__":
    unittest.main()
