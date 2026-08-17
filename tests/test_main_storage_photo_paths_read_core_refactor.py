"""Dry-run guard for storage photo-path property Core read."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_storage_photo_paths_read_core.py"
MAIN = ROOT / "main.py"


def _transform():
    spec = importlib.util.spec_from_file_location("storage_photo_paths_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainStoragePhotoPathsReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index('async def _storage_rutas_fotos_de_usuario')
        end = source.index('\n\nasync def _storage_borrar_carpeta_usuario', start)
        return source[start:end]

    def test_transform_compiles_and_removes_only_direct_property_get(self):
        transformed = _transform()(self.source)
        block = self._block(transformed)
        self.assertNotIn('r = await client.get(\n                f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        compile(transformed, "main.py", "exec")

    def test_core_read_preserves_fail_soft_and_boundary(self):
        transformed = _transform()(self.source)
        block = self._block(transformed)
        self.assertIn('filas = await get_rows(', block)
        self.assertIn('"propiedades",', block)
        self.assertIn('{"user_id": f"eq.{user_id}", "select": "fotos", "limit": "10000"}', block)
        self.assertIn('timeout=30', block)
        self.assertIn('except httpx.HTTPStatusError:\n            filas = []', block)
        self.assertIn('except Exception as e:', block)
        self.assertIn('return {b: sorted(v) for b, v in rutas.items()}', block)
        # Destructive/storage helper is deliberately outside this transform boundary.
        self.assertIn('async def _storage_borrar_carpeta_usuario', transformed)
        self.assertIn('f"{SUPABASE_URL}/rest/v1/rpc/admin_eliminar_usuario_total"', transformed)


if __name__ == "__main__":
    unittest.main()
