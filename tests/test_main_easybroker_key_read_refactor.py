"""Dry-run guard for the organization-scoped EasyBroker key read migration."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from scripts.refactor_main_easybroker_key_read import transform

ROOT = Path(__file__).resolve().parents[1]


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return ast.get_source_segment(source, node) or ""


class MainEasyBrokerKeyReadRefactorTests(unittest.TestCase):
    def test_transform_moves_only_key_read_to_core_and_preserves_scope(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        before = function_source(source, "get_eb_key_for_user")
        updated = transform(source)
        after = function_source(updated, "get_eb_key_for_user")

        self.assertIn("/rest/v1/user_integrations", before)
        self.assertNotIn("/rest/v1/user_integrations", after)
        self.assertIn('rows = await get_rows(', after)
        self.assertIn('"user_integrations"', after)
        self.assertIn("org_id = await get_org_id_for_user(user_id)", after)
        self.assertIn('"provider": "eq.easybroker"', after)
        self.assertIn('"select": "api_key"', after)
        self.assertIn("except Exception:\n        return None", after)
        self.assertEqual(
            updated.count("/rest/v1/user_integrations"),
            source.count("/rest/v1/user_integrations") - 1,
        )
        compile(updated, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
