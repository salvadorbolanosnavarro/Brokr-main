"""Permanent guards for self-account deletion PostgREST routing through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainSelfAccountDeleteCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('tablas = ["propiedades", "contactos", "contratos", "user_integrations",')
        start = cls.source.rfind('@app.', 0, start)
        end = cls.source.index('\n\n# ════════════════════════════════════════════════════════════════\n# Instagram', start)
        cls.block = cls.source[start:end]

    def test_subscription_lookup_uses_exact_200_service_read(self):
        block = self.block
        self.assertIn('sub_rows = await get_service_json(', block)
        self.assertIn('"suscripciones"', block)
        self.assertIn('accepted_statuses=(200,)', block)
        self.assertIn('except httpx.HTTPStatusError:\n                    sub_rows = []', block)
        self.assertNotIn('/rest/v1/suscripciones', block)

    def test_photo_lookup_uses_exact_200_service_read_before_storage_deletes(self):
        block = self.block
        self.assertIn('filas_fotos = await get_service_json(', block)
        self.assertIn('"propiedades"', block)
        self.assertIn('accepted_statuses=(200,)', block)
        self.assertNotIn('/rest/v1/propiedades', block)
        self.assertLess(block.index('filas_fotos = await get_service_json('), block.index('/storage/v1/object/fotos-propiedades/'))

    def test_table_deletes_preserve_ledger_and_exact_status_contract(self):
        block = self.block
        self.assertIn('for tabla in tablas:', block)
        self.assertIn('await delete_rows(\n                    tabla,', block)
        self.assertIn('{"user_id": f"eq.{user_id}"}', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('errores.append(f"{tabla}: {e.response.status_code} {e.response.text[:120]}")', block)
        self.assertIn('except Exception as e:\n                errores.append(f"{tabla}: {e}")', block)
        self.assertNotIn('/rest/v1/{tabla}', block)

    def test_usuario_delete_preserves_http_fail_without_error_entry(self):
        block = self.block
        self.assertIn('await delete_rows(\n                "usuarios",', block)
        self.assertIn('{"id": f"eq.{user_id}"}', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('borrados["usuarios"] = False', block)
        self.assertNotIn('/rest/v1/usuarios?id=eq.', block)

    def test_storage_and_auth_apis_remain_separate_from_postgrest_core(self):
        block = self.block
        self.assertIn('/storage/v1/object/fotos-propiedades/', block)
        self.assertIn('/auth/v1/admin/users/{user_id}', block)
        self.assertNotIn('/rest/v1/', block)


if __name__ == "__main__":
    unittest.main()
