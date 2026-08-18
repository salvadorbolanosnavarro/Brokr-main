"""Dry-run guard for trial-max subscription POST Core routing."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_trial_max_subscription_post_core.py"

spec = importlib.util.spec_from_file_location("trial_max_subscription_post_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainTrialMaxSubscriptionPostTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.transformed = transform.transform_source(cls.source)

    def test_transform_is_exact_and_compiles(self):
        compile(self.transformed, "main.py", "exec")
        self.assertEqual(MAIN.read_text(encoding="utf-8"), self.source)
        self.assertEqual(self.transformed.count(transform.NEW), 1)
        self.assertNotIn(transform.OLD, self.transformed)
        if transform.OLD in self.source:
            self.assertEqual(self.source.count(transform.OLD), 1)
            self.assertEqual(self.transformed, self.source.replace(transform.OLD, transform.NEW, 1))
        else:
            self.assertEqual(self.source.count(transform.NEW), 1)
            self.assertEqual(self.transformed, self.source)

    def test_http_and_transport_contract_are_preserved(self):
        new = transform.NEW
        self.assertIn('await post_rows(', new)
        self.assertIn('"suscripciones"', new)
        self.assertIn('fila,', new)
        self.assertIn('prefer="return=minimal"', new)
        self.assertIn('timeout=10', new)
        self.assertIn('accepted_statuses=(200, 201)', new)
        self.assertIn('except httpx.HTTPStatusError:', new)
        self.assertIn('raise HTTPException(status_code=502, detail="No se pudo activar la prueba. Intenta de nuevo.")', new)
        self.assertNotIn('except Exception', new)
        self.assertNotIn('/rest/v1/suscripciones', new)

    def test_trial_burn_patch_is_deliberately_outside_transform(self):
        self.assertNotIn('/rest/v1/usuarios', transform.OLD)
        self.assertNotIn('/rest/v1/usuarios', transform.NEW)
        self.assertNotIn('await patch_rows(', transform.NEW)


if __name__ == "__main__":
    unittest.main()
