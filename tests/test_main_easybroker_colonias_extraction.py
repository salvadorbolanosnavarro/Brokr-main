"""Permanent guards for EasyBroker colonia autocomplete extraction."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_colonias.py"
CORE = ROOT / "core" / "easybroker.py"


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return ast.get_source_segment(source, node) or ""


class EasyBrokerColoniasExtractionTests(unittest.TestCase):
    def test_shared_location_helpers_and_route_preserve_contract(self):
        main = MAIN.read_text(encoding="utf-8")
        router = ROUTER.read_text(encoding="utf-8")
        core = CORE.read_text(encoding="utf-8")
        route = function_source(router, "get_colonias")

        self.assertIn('def extract_colonia(location_str: str) -> str:', core)
        self.assertIn('def normalize(s: str) -> str:', core)
        self.assertIn('@router.get("/colonias")', router)
        self.assertIn('Query("", min_length=2)', route)
        self.assertIn('ciudad: str = "Morelia"', route)
        self.assertIn('if not EB_API_KEY:', route)
        self.assertIn('cache_key = f"colonias_{normalize(ciudad)}"', route)
        self.assertIn('httpx.AsyncClient(timeout=30)', route)
        self.assertIn('while page <= 80:', route)
        self.assertIn('cache_set(cache_key, colonias_map)', route)
        self.assertIn('matches[:12]', route)
        self.assertIn(
            'from core.easybroker import EB_API_KEY, EB_BASE, _EB_LOTE, _EB_PAUSA_LOTE, _eb_get_reintentos, eb_headers, extract_colonia, normalize',
            main,
        )
        self.assertIn(
            'from routers.easybroker_colonias import router as easybroker_colonias_router',
            main,
        )
        self.assertNotIn('@app.get("/colonias")', main)
        self.assertNotIn('def extract_colonia(', main)
        self.assertNotIn('def normalize(s: str)', main)
        compile(core, "core/easybroker.py", "exec")
        compile(router, "routers/easybroker_colonias.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
