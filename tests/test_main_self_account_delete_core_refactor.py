"""Permanent guards for self-account deletion ("Eliminar mi cuenta").

The deletion must be atomic: it goes through the same database function as
the admin console (``admin_eliminar_usuario_total``), so either everything is
deleted (including ``auth.users``) or nothing is. The old sequence deleted
tables one by one, then ``usuarios``, then ``auth.users`` separately; for any
organization owner the last step failed (``organizaciones.owner_id`` is ON
DELETE RESTRICT) and left a live account with no ``usuarios`` row and no
subscription.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "account_delete.py"


class SelfAccountDeleteAtomicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_uses_atomic_rpc(self):
        self.assertIn('"admin_eliminar_usuario_total"', self.block)
        self.assertIn('{"p_user_id": user_id}', self.block)

    def test_no_piecemeal_table_or_auth_deletes(self):
        block = self.block
        self.assertNotIn("delete_rows(", block)
        self.assertNotIn("for tabla in tablas", block)
        self.assertNotIn("/auth/v1/admin/users/", block)
        self.assertNotIn("/rest/v1/", block)

    def test_rpc_failure_is_an_http_error_not_ok_true(self):
        block = self.block
        rpc = block.index('"admin_eliminar_usuario_total"')
        ok = block.index('return {"ok": True')
        self.assertIn("raise HTTPException(\n            status_code=500", block[rpc:ok])
        self.assertIn('resultado.get("ok")', block[rpc:ok])

    def test_subscription_and_photos_are_read_before_the_delete(self):
        block = self.block
        rpc = block.index('"admin_eliminar_usuario_total"')
        self.assertLess(block.index("sub_rows = await get_service_json("), rpc)
        self.assertLess(block.index("rutas_fotos = await _storage_rutas_fotos_de_usuario("), rpc)

    def test_stripe_cancel_and_storage_only_after_confirmed_delete(self):
        block = self.block
        rpc = block.index('"admin_eliminar_usuario_total"')
        self.assertGreater(block.index("https://api.stripe.com/v1/subscriptions/"), rpc)
        self.assertGreater(block.index("await _storage_borrar_carpeta_usuario("), rpc)

    def test_frontend_contract_keys_preserved(self):
        block = self.block
        self.assertIn('borrados["auth"] = True', block)
        self.assertIn('"borrados": borrados', block)
        self.assertIn('"errores": errores', block)


if __name__ == "__main__":
    unittest.main()
