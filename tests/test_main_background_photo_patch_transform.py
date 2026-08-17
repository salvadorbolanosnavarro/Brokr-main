"""Dry-run guard for the background photo-migration PATCH Core migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_background_photo_patch_core.py"

spec = importlib.util.spec_from_file_location("background_photo_patch_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainBackgroundPhotoPatchTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.transformed = transform.transform_source(cls.source)

    def test_transform_is_exact_and_compiles(self):
        compile(self.transformed, "main.py", "exec")
        self.assertEqual(MAIN.read_text(encoding="utf-8"), self.source)
        self.assertEqual(self.transformed.count(transform.NEW), 1)
        self.assertNotIn(transform.OLD, self.transformed)
        if transform.OLD in self.source:
            self.assertEqual(self.source.count(transform.OLD), 1)
            self.assertEqual(self.transformed, self.source.replace(transform.OLD, transform.NEW, 1))
        else:
            self.assertEqual(self.source.count(transform.NEW), 1)
            self.assertEqual(self.transformed, self.source)

    def test_http_failures_still_count_but_transport_failures_do_not(self):
        new = transform.NEW
        self.assertIn('await patch_rows(', new)
        self.assertIn('"propiedades"', new)
        self.assertIn('{"id": f"eq.{fila.get(\'id\')}"}', new)
        self.assertIn('{"fotos": nuevas}', new)
        self.assertIn('timeout=30.0', new)
        self.assertIn('except httpx.HTTPStatusError:\n                            pass', new)
        http_except = new.index('except httpx.HTTPStatusError:')
        counter = new.index('total_props += 1')
        outer_except = new.index('except Exception:')
        self.assertLess(http_except, counter)
        self.assertLess(counter, outer_except)
        self.assertIn('total_fotos += subidas', new)
        self.assertNotIn('/rest/v1/', new)


if __name__ == "__main__":
    unittest.main()
