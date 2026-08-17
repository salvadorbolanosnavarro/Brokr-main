"""Permanent guard for best-effort trial-expiry PATCH Core routing."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, ast.AsyncFunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


class MainTrialExpiryPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.function = async_function_source(cls.source, "_expirar_trial_suscripcion")

    def test_expiry_patch_delegates_to_core(self):
        fn = self.function
        self.assertIn('await patch_rows(', fn)
        self.assertIn('"suscripciones"', fn)
        self.assertIn('{"id": f"eq.{sub_id}"}', fn)
        self.assertIn('"status": "expired"', fn)
        self.assertIn('datetime.utcnow().isoformat()', fn)
        self.assertIn('timeout=8', fn)
        self.assertNotIn('/rest/v1/suscripciones', fn)
        self.assertNotIn('SUPABASE_SERVICE_KEY', fn)

    def test_best_effort_contract_stays_intact(self):
        fn = self.function
        self.assertIn('if not sub_id:\n        return', fn)
        self.assertIn('except Exception:\n        pass', fn)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
