"""Permanent guard for website-lead existing-contact PATCH Core routing."""
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


class MainWebsiteLeadExistingPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.function = async_function_source(cls.source, "sitio_registrar_lead")

    def test_existing_contact_patch_delegates_to_core(self):
        fn = self.function
        self.assertIn('await patch_rows(', fn)
        self.assertIn('"contactos"', fn)
        self.assertIn('{"id": f"eq.{existente[\'id\']}"}', fn)
        self.assertIn('"es_potencial": True', fn)
        self.assertIn('"notas": nuevas_notas[:5000]', fn)
        self.assertIn('"updated_at": ahora', fn)
        self.assertIn('timeout=10', fn)

    def test_legacy_http_fail_soft_and_duplicate_response_stay_intact(self):
        fn = self.function
        patch_start = fn.index('await patch_rows(')
        duplicate_return = fn.index('return {"ok": True, "duplicado": True}', patch_start)
        patch_block = fn[patch_start:duplicate_return]
        self.assertIn('except httpx.HTTPStatusError:', patch_block)
        self.assertNotIn('except Exception', patch_block)
        self.assertNotIn('/rest/v1/contactos', patch_block)
        self.assertIn('return {"ok": True, "duplicado": True}', fn)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
