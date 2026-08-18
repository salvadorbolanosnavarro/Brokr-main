"""Permanent guard for website-lead contact dedup read delegated to Core."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "public_site_leads.py"


def async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.AsyncFunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


def core_database_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    return {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "core.database"
        for alias in node.names
    }


class MainWebsiteLeadContactReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")
        cls.function = async_function_source(cls.source, "sitio_registrar_lead")

    def test_contact_dedup_read_delegates_to_core_database(self):
        fn = self.function
        self.assertIn("get_rows", core_database_imports(self.source))
        self.assertNotIn('/rest/v1/contactos', fn)
        self.assertIn('filas = await get_rows(', fn)
        self.assertIn('"contactos"', fn)
        self.assertIn('"user_id": f"eq.{user_id}"', fn)
        self.assertIn('"telefono": f"eq.{telefono}"', fn)
        self.assertIn('"select": "id,notas,es_potencial"', fn)
        self.assertIn('"limit": "1"', fn)
        self.assertIn("timeout=10", fn)
        self.assertIn("existente = filas[0] if filas else None", fn)

    def test_legacy_http_rejection_semantics_are_preserved(self):
        fn = self.function
        self.assertIn(
            "except httpx.HTTPStatusError:\n                filas = []",
            fn,
        )
        dedup_start = fn.index("existente = None")
        existente_at = fn.index("if existente:", dedup_start)
        dedup = fn[dedup_start:existente_at]
        self.assertNotIn("except Exception", dedup)
        self.assertNotIn("except httpx.RequestError", dedup)
        compile(self.source, "routers/public_site_leads.py", "exec")


if __name__ == "__main__":
    unittest.main()
