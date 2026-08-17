"""Contract guards for RLS-preserving public reads in core.database."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "core" / "database.py"


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


class CoreDatabasePublicReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DB.read_text(encoding="utf-8")

    def test_public_headers_use_only_public_supabase_credentials(self):
        src = function_source(self.source, "public_headers")
        self.assertIn("settings.require_supabase_public()", src)
        self.assertIn('"apikey": settings.supabase_anon_key', src)
        self.assertIn('f"Bearer {settings.supabase_anon_key}"', src)
        self.assertNotIn("supabase_service_key", src)

    def test_service_and_public_reads_share_one_request_implementation(self):
        service_src = function_source(self.source, "get_rows")
        public_src = function_source(self.source, "get_public_rows")
        shared_src = function_source(self.source, "_get_rows")

        self.assertIn("return await _get_rows(", service_src)
        self.assertIn("headers=service_headers()", service_src)
        self.assertNotIn("public_headers", service_src)

        self.assertIn("return await _get_rows(", public_src)
        self.assertIn("headers=public_headers()", public_src)
        self.assertNotIn("service_headers", public_src)

        self.assertIn("response.raise_for_status()", shared_src)
        self.assertIn("payload = response.json()", shared_src)
        self.assertIn("if not isinstance(payload, list):", shared_src)
        self.assertIn('raise RuntimeError(f"Unexpected Supabase response for table {table}")', shared_src)
        compile(self.source, str(DB), "exec")


if __name__ == "__main__":
    unittest.main()
