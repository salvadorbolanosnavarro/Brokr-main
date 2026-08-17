"""Dry-run guard for AVM public propiedades_avm fallback Core migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_avm_public_fallback_core.py"

spec = importlib.util.spec_from_file_location("avm_public_fallback_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainAvmPublicFallbackTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.transformed = transform.transform_source(cls.source)

    def test_transform_is_bounded_and_compiles(self):
        compile(self.transformed, "main.py", "exec")
        self.assertEqual(MAIN.read_text(encoding="utf-8"), self.source)
        self.assertEqual(self.transformed.count(transform.NEW), 1)
        self.assertNotIn(transform.OLD, self.transformed)
        self.assertEqual(self.transformed.count(transform.NEW_IMPORT), 1)

        if transform.OLD in self.source:
            expected = self.source.replace(transform.OLD_IMPORT, transform.NEW_IMPORT, 1)
            expected = expected.replace(transform.OLD, transform.NEW, 1)
            self.assertEqual(self.transformed, expected)
        else:
            self.assertEqual(self.source.count(transform.NEW), 1)
            self.assertEqual(self.transformed, self.source)

    def test_public_rls_and_legacy_http_fail_soft_are_preserved(self):
        new = transform.NEW
        self.assertIn('await get_public_rows(', new)
        self.assertIn('"propiedades_avm"', new)
        self.assertIn('"ciudad": "eq.Morelia"', new)
        self.assertIn('"precio": "gt.0"', new)
        self.assertIn('"metros_construccion": "not.is.null"', new)
        self.assertIn('"limit": req.max_resultados', new)
        self.assertIn('"order": "precio.asc"', new)
        self.assertIn('timeout=15', new)
        self.assertIn('except httpx.HTTPStatusError:\n            items = []', new)
        self.assertNotIn('get_rows(', new)
        self.assertNotIn('SUPABASE_SERVICE_KEY', new)
        self.assertNotIn('except Exception', new)

    def test_rpc_and_post_processing_are_not_part_of_transform(self):
        changed_old = transform.OLD
        changed_new = transform.NEW
        self.assertNotIn('rpc/buscar_cercanos', changed_old)
        self.assertNotIn('rpc/buscar_cercanos', changed_new)
        self.assertNotIn('comparables.append', changed_old)
        self.assertNotIn('comparables.append', changed_new)


if __name__ == "__main__":
    unittest.main()
