"""Permanent guard for background photo-migration PATCH Core routing."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, ast.AsyncFunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


class MainBackgroundPhotoPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.function = async_function_source(cls.source, "_migrar_fotos_org")

    def test_photo_patch_delegates_to_core(self):
        fn = self.function
        self.assertIn('await patch_rows(', fn)
        self.assertIn('"propiedades"', fn)
        self.assertIn('{"id": f"eq.{fila.get(\'id\')}"}', fn)
        self.assertIn('{"fotos": nuevas}', fn)
        self.assertIn('timeout=30.0', fn)
        self.assertNotIn('/rest/v1/propiedades', fn)

    def test_legacy_counter_semantics_stay_intact(self):
        fn = self.function
        patch_start = fn.index('await patch_rows(')
        http_except = fn.index('except httpx.HTTPStatusError:', patch_start)
        props_counter = fn.index('total_props += 1', http_except)
        photos_counter = fn.index('total_fotos += subidas', props_counter)
        outer_except = fn.index('except Exception:', photos_counter)
        self.assertLess(http_except, props_counter)
        self.assertLess(props_counter, photos_counter)
        self.assertLess(photos_counter, outer_except)
        self.assertIn('await asyncio.sleep(0.3)', fn)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
