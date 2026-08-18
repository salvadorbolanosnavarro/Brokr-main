"""Permanent guard for the legacy EasyBroker catalog extraction."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "easybroker_catalog.py"
MAIN = ROOT / "main.py"


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return ast.get_source_segment(source, node) or ""


class EasyBrokerCatalogExtractionTests(unittest.TestCase):
    def test_catalog_route_preserves_legacy_contract(self):
        router = ROUTER.read_text(encoding="utf-8")
        main = MAIN.read_text(encoding="utf-8")
        function = function_source(router, "get_propiedades")

        self.assertIn('@router.get("/propiedades")', router)
        self.assertIn('if not EB_API_KEY:', function)
        self.assertIn('status_code=500, detail="EB_API_KEY no configurada"', function)
        self.assertIn('httpx.AsyncClient(timeout=15)', function)
        self.assertIn('f"{EB_BASE}/properties"', function)
        self.assertIn('headers=eb_headers()', function)
        self.assertIn('params={"page": page, "limit": limit}', function)
        self.assertIn('if r.status_code != 200:', function)
        self.assertIn('status_code=r.status_code, detail="Error EasyBroker"', function)
        self.assertIn('return r.json()', function)

        self.assertIn(
            'from routers.easybroker_catalog import router as easybroker_catalog_router',
            main,
        )
        self.assertNotIn('@app.get("/propiedades")', main)
        compile(router, "routers/easybroker_catalog.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
