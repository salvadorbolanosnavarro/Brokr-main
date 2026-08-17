"""Permanent regression guard for the AVM public propiedades_avm fallback migration."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        n for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == name
    )
    return ast.get_source_segment(source, node) or ""


class MainAvmPublicFallbackCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.func = async_function_source(cls.source, "comparables_cercanos")

    def test_fallback_delegates_to_public_core_without_privilege_escalation(self):
        tree = ast.parse(self.source)
        core_imports = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "core.database"
            for alias in node.names
        }
        self.assertIn("get_public_rows", core_imports)
        self.assertIn('items = await get_public_rows(', self.func)
        self.assertIn('"propiedades_avm"', self.func)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/propiedades_avm"', self.func)
        self.assertNotIn("SUPABASE_SERVICE_KEY", self.func)

    def test_fallback_filters_and_fail_soft_semantics_stay_intact(self):
        func = self.func
        self.assertIn('"ciudad": "eq.Morelia"', func)
        self.assertIn('"precio": "gt.0"', func)
        self.assertIn('"metros_construccion": "not.is.null"', func)
        self.assertIn('"limit": req.max_resultados', func)
        self.assertIn('"order": "precio.asc"', func)
        self.assertIn('timeout=15', func)
        self.assertIn('except httpx.HTTPStatusError:', func)
        self.assertIn('items = []', func)

    def test_postgis_rpc_and_result_mapping_remain_present(self):
        func = self.func
        self.assertIn('f"{SUPABASE_URL}/rest/v1/rpc/buscar_cercanos"', func)
        self.assertIn('if r.status_code not in (200, 201):', func)
        self.assertIn('items = r.json() or []', func)
        self.assertIn('comparables.append({', func)
        self.assertIn('cache_set(cache_key, resultado, ttl=3600)', func)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
