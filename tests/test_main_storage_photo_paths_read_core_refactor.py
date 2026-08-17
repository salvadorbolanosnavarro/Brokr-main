"""Permanent guard for storage photo-path property Core read."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainStoragePhotoPathsReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self) -> str:
        start = self.source.index('async def _storage_rutas_fotos_de_usuario')
        end = self.source.index('\n\nasync def _storage_borrar_carpeta_usuario', start)
        return self.source[start:end]

    def test_direct_property_get_stays_removed(self):
        block = self._block()
        self.assertNotIn('r = await client.get(\n                f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        compile(self.source, "main.py", "exec")

    def test_core_read_preserves_fail_soft_and_destructive_boundary(self):
        block = self._block()
        self.assertIn('filas = await get_rows(', block)
        self.assertIn('"propiedades",', block)
        self.assertIn('{"user_id": f"eq.{user_id}", "select": "fotos", "limit": "10000"}', block)
        self.assertIn('timeout=30', block)
        self.assertIn('except httpx.HTTPStatusError:\n            filas = []', block)
        self.assertIn('except Exception as e:', block)
        self.assertIn('return {b: sorted(v) for b, v in rutas.items()}', block)
        self.assertIn('async def _storage_borrar_carpeta_usuario', self.source)
        self.assertIn('f"{SUPABASE_URL}/rest/v1/rpc/admin_eliminar_usuario_total"', self.source)


if __name__ == "__main__":
    unittest.main()
