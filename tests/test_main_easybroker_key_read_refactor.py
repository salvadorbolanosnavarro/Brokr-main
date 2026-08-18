"""Permanent guard for the organization-scoped EasyBroker key read migration."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "easybroker_config.py"
MAIN = ROOT / "main.py"


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return ast.get_source_segment(source, node) or ""


class MainEasyBrokerKeyReadRefactorTests(unittest.TestCase):
    def test_key_read_delegates_to_core_and_preserves_org_scope(self):
        source = ROUTER.read_text(encoding="utf-8")
        main = MAIN.read_text(encoding="utf-8")
        function = function_source(source, "get_eb_key_for_user")

        self.assertNotIn("/rest/v1/user_integrations", function)
        self.assertIn('rows = await get_rows(', function)
        self.assertIn('"user_integrations"', function)
        self.assertIn("org_id = await get_org_id_for_user(user_id)", function)
        self.assertIn('"provider": "eq.easybroker"', function)
        self.assertIn('"select": "api_key"', function)
        self.assertIn('"limit": "1"', function)
        self.assertIn("timeout=8", function)
        self.assertIn("except Exception:\n        return None", function)
        self.assertIn(
            'from routers.easybroker_config import get_eb_key_for_user, router as easybroker_config_router',
            main,
        )
        self.assertNotIn('async def get_eb_key_for_user(', main)
        compile(source, "routers/easybroker_config.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
