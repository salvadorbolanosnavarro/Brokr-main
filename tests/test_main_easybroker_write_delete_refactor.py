"""Dry-run guard for EasyBroker save/disconnect migration to Core DB."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from scripts.refactor_main_easybroker_write_delete import transform

ROOT = Path(__file__).resolve().parents[1]


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return ast.get_source_segment(source, node) or ""


class MainEasyBrokerWriteDeleteRefactorTests(unittest.TestCase):
    def test_transform_moves_only_easybroker_save_and_delete_to_core(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        before_set = function_source(source, "set_eb_key")
        before_delete = function_source(source, "delete_eb_key")
        updated = transform(source)
        after_set = function_source(updated, "set_eb_key")
        after_delete = function_source(updated, "delete_eb_key")

        self.assertIn("/rest/v1/user_integrations", before_set)
        self.assertIn("/rest/v1/user_integrations", before_delete)
        self.assertNotIn("/rest/v1/user_integrations", after_set)
        self.assertNotIn("/rest/v1/user_integrations", after_delete)
        self.assertIn("from core.database import delete_rows, get_rows, post_rows", updated)
        self.assertIn('await post_rows(', after_set)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', after_set)
        self.assertIn('except httpx.HTTPStatusError as e:', after_set)
        self.assertIn('No se pudo guardar la API key (Supabase {status})', after_set)
        self.assertIn('await delete_rows(', after_delete)
        self.assertIn('"org_id": f"eq.{await get_org_id_for_user(user_id)}"', after_delete)
        self.assertIn('"provider": "eq.easybroker"', after_delete)
        self.assertIn('except httpx.HTTPStatusError:', after_delete)
        self.assertEqual(
            updated.count("/rest/v1/user_integrations"),
            source.count("/rest/v1/user_integrations") - 2,
        )
        compile(updated, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
