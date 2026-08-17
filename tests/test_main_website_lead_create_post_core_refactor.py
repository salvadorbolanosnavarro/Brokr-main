"""Permanent guard for website-lead creation POST Core routing."""
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


class MainWebsiteLeadCreatePostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.function = async_function_source(cls.source, "sitio_registrar_lead")

    def test_new_lead_post_delegates_to_core(self):
        fn = self.function
        self.assertIn('await post_rows(', fn)
        self.assertIn('"contactos"', fn)
        self.assertIn('nuevo,', fn)
        self.assertIn('prefer="return=minimal"', fn)
        self.assertIn('timeout=10', fn)
        self.assertIn('accepted_statuses=(200, 201)', fn)

    def test_exact_legacy_error_contract_stays_intact(self):
        fn = self.function
        post_start = fn.index('await post_rows(')
        final_return = fn.rindex('return {"ok": True}')
        post_block = fn[post_start:final_return]
        self.assertIn('except httpx.HTTPStatusError:', post_block)
        self.assertIn('raise HTTPException(status_code=502, detail="No se pudo registrar el lead")', post_block)
        self.assertNotIn('except Exception', post_block)
        self.assertNotIn('/rest/v1/contactos', post_block)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
