"""Guards for admin_list_users' subscriptions lookup migration to Core."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_admin_subscriptions_lookup_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("admin_subscriptions_lookup_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainAdminSubscriptionsLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_one_direct_subscriptions_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/suscripciones") - transformed.count("/rest/v1/suscripciones")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_admin_subscriptions_lookup_preserves_fail_soft_http_contract(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.get("/admin/users")')
        end = transformed.index('class AdminRolReq(BaseModel):', start)
        block = transformed[start:end]

        self.assertIn('subs = await get_rows(\n            "suscripciones",', block)
        self.assertIn('"select": "user_id,plan_id,plan_nombre,status,updated_at"', block)
        self.assertIn('"order": "updated_at.desc"', block)
        self.assertIn('"limit": "10000"', block)
        self.assertIn("timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError:\n        subs = []", block)
        self.assertIn("for s in subs:", block)
        lookup = block.split("# 3) Merge", 1)[0]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/suscripciones", lookup)
        # The already-migrated usuarios read stays in Core and is not reverted.
        self.assertIn('users = await get_rows(\n            "usuarios",', block)


if __name__ == "__main__":
    unittest.main()
