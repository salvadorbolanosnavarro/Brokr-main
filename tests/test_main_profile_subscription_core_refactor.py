"""Dry-run guards for /profile/status subscription read migration to Core."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_profile_subscription_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("profile_subscription_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainProfileSubscriptionCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_or_keeps_migrated_read(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.get("/profile/status")')
        end = transformed.index("\n@app.", start + 1)
        before = self.source[self.source.index('@app.get("/profile/status")'):self.source.index("\n@app.", self.source.index('@app.get("/profile/status")') + 1)]
        after = transformed[start:end]
        delta = before.count("/rest/v1/suscripciones") - after.count("/rest/v1/suscripciones")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_profile_subscription_uses_core_and_keeps_fail_soft_trial_logic(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.get("/profile/status")')
        end = transformed.index("\n@app.", start + 1)
        block = transformed[start:end]

        self.assertIn('sub_rows = await get_rows(\n                "suscripciones",', block)
        self.assertIn('"org_id": f"eq.{_oid}"', block)
        self.assertIn('"select": "*"', block)
        self.assertIn('"order": "updated_at.desc"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=6", block)
        self.assertIn("if sub_rows:\n                row = sub_rows[0]", block)
        self.assertIn('_st = row.get("status")', block)
        self.assertIn('_act = _st in ("active", "trialing")', block)
        self.assertIn('_trial_ya_vencio(row.get("trial_hasta"))', block)
        self.assertIn('asyncio.create_task(_expirar_trial_suscripcion(row.get("id")))', block)
        self.assertIn('sub_state = {"active": False, "plan": None, "status": "sin_suscripcion"}', block)
        self.assertIn("except Exception:\n        pass", block)
        self.assertNotIn("/rest/v1/suscripciones", block)


if __name__ == "__main__":
    unittest.main()
