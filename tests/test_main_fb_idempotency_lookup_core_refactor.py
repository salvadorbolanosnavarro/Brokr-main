"""Dry-run guards for _fb_buscar_por_idempotencia Core migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_fb_idempotency_lookup_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("fb_idempotency_lookup_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainFbIdempotencyLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index("async def _fb_buscar_por_idempotencia(")
        end = source.index("\n\nasync def _fb_actualizar_entidad(", start)
        return source[start:end]

    def test_transform_compiles_and_removes_direct_get(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertNotIn("/rest/v1/", block)
        compile(transformed, "main.py", "exec")

    def test_core_lookup_preserves_fail_soft_contract(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)

        self.assertIn('filas = await get_rows(\n                _FB_TABLA_ENTIDADES,', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"idempotency_key": f"eq.{idempotency_key}"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError as e:", block)
        self.assertIn("if _fb_tabla_falta(e.response):", block)
        self.assertIn('_fb_avisa_migracion("buscar idempotencia", e.response)', block)
        self.assertIn('except Exception as e:\n        _fb_log.error("Error buscando idempotencia: %s", e)', block)
        self.assertIn("if filas:\n            return filas[0]", block)
        self.assertTrue(block.rstrip().endswith("return {}"))
        self.assertNotIn("Authorization", block)
        self.assertNotIn("_sb_headers", block)


if __name__ == "__main__":
    unittest.main()
