"""Permanent regression guard for EasyBroker save/disconnect Core DB migration."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return ast.get_source_segment(source, node) or ""


class MainEasyBrokerWriteDeleteRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "main.py").read_text(encoding="utf-8")

    def test_easybroker_save_and_delete_delegate_to_core_database(self):
        source = self.source
        set_src = function_source(source, "set_eb_key")
        delete_src = function_source(source, "delete_eb_key")
        tree = ast.parse(source)
        core_database_imports = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "core.database"
            for alias in node.names
        }

        self.assertTrue({"delete_rows", "get_rows", "post_rows"} <= core_database_imports)
        self.assertNotIn("/rest/v1/user_integrations", set_src)
        self.assertNotIn("/rest/v1/user_integrations", delete_src)
        self.assertIn('await post_rows(', set_src)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', set_src)
        self.assertIn('except httpx.HTTPStatusError as e:', set_src)
        self.assertIn('No se pudo guardar la API key (Supabase {status})', set_src)
        self.assertIn('await delete_rows(', delete_src)
        self.assertIn('"org_id": f"eq.{await get_org_id_for_user(user_id)}"', delete_src)
        self.assertIn('"provider": "eq.easybroker"', delete_src)
        self.assertIn('except httpx.HTTPStatusError:', delete_src)
        self.assertIn('return {"ok": True, "deleted": True}', delete_src)

    def test_easybroker_write_delete_security_and_validation_stay_intact(self):
        set_src = function_source(self.source, "set_eb_key")
        delete_src = function_source(self.source, "delete_eb_key")
        self.assertIn("user_id = await exigir_gestion_integraciones(request)", set_src)
        self.assertIn("user_id = await exigir_gestion_integraciones(request)", delete_src)
        self.assertIn('f"{EB_BASE}/properties?limit=1"', set_src)
        self.assertIn("if test.status_code == 401:", set_src)
        self.assertIn('"org_id": await get_org_id_for_user(user_id)', set_src)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
