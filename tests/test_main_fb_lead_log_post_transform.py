"""Dry-run guard for Facebook lead-log POST Core migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_fb_lead_log_post_core.py"

spec = importlib.util.spec_from_file_location("fb_lead_log_post_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainFbLeadLogPostTransformTests(unittest.TestCase):
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

    def test_legacy_duplicate_missing_table_and_logging_contract_is_preserved(self):
        new = transform.NEW
        self.assertIn('await post_rows(', new)
        self.assertIn('"fb_leads_recibidos"', new)
        self.assertIn('{**bitacora, **extra}', new)
        self.assertIn('prefer="return=minimal"', new)
        self.assertIn('timeout=10', new)
        self.assertIn('accepted_statuses=(200, 201, 204)', new)
        self.assertIn('except httpx.HTTPStatusError as e:', new)
        self.assertIn('e.response.status_code != 409', new)
        self.assertIn('not _fb_tabla_falta(e.response)', new)
        self.assertIn('leadgen_id, e.response.status_code', new)
        self.assertIn('(e.response.text or "")[:200]', new)
        self.assertIn('except Exception as e:', new)
        self.assertIn('_fb_log.error("Error anotando el lead %s: %s", leadgen_id, e)', new)
        self.assertNotIn('/rest/v1/', new)


if __name__ == "__main__":
    unittest.main()
