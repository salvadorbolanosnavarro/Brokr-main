"""Permanent guards for the Lead Ads page-owner Core database contract."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "facebook_leadgen_processor.py"


def async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, ast.AsyncFunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


class MainFacebookPageOwnerCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CORE.read_text(encoding="utf-8")
        cls.block = async_function_source(cls.source, "find_facebook_page_owner")

    def test_core_compiles(self):
        compile(self.source, "core/facebook_leadgen_processor.py", "exec")

    def test_page_owner_keeps_like_then_fallback_and_fail_soft_contract(self):
        block = self.block
        self.assertEqual(block.count("await get_rows("), 2)
        self.assertEqual(block.count('"user_integrations"'), 2)
        self.assertIn('"meta": f"like.*{page_id}*"', block)
        self.assertIn('"limit": "20"', block)
        self.assertIn('"limit": "500"', block)
        self.assertEqual(block.count("except httpx.HTTPStatusError:"), 2)
        self.assertEqual(block.count("rows = []"), 2)
        self.assertIn(
            'except Exception as exc:\n        _log.error("Error buscando al dueño de la página %s: %s", page_id, exc)\n        return {}',
            block,
        )
        self.assertIn('decrypt_facebook_secret(row.get("api_key", ""))', block)
        self.assertNotIn("/rest/v1/user_integrations", block)
        self.assertNotIn("headers=_sb_headers()", block)


if __name__ == "__main__":
    unittest.main()
