"""Dry-run guard for demo scheduling POST Core migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_demo_create_post_core.py"

spec = importlib.util.spec_from_file_location("demo_create_post_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainDemoCreatePostTransformTests(unittest.TestCase):
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

    def test_exact_legacy_status_contract_is_preserved(self):
        new = transform.NEW
        self.assertIn('await post_rows(', new)
        self.assertIn('"demos_agendadas"', new)
        self.assertIn('fila,', new)
        self.assertIn('prefer="return=minimal"', new)
        self.assertIn('timeout=10', new)
        self.assertIn('accepted_statuses=(200, 201)', new)
        self.assertIn('except httpx.HTTPStatusError:', new)
        self.assertIn('raise HTTPException(status_code=502, detail="No se pudo agendar. Intenta de nuevo en un momento.")', new)
        self.assertNotIn('except Exception', new)
        self.assertNotIn('/rest/v1/', new)

    def test_email_notification_flow_stays_after_persistence(self):
        self.assertIn('# Aviso por correo. Si Resend falla, la demo ya quedó guardada: no se rompe.', self.transformed)
        self.assertIn('if _RESEND_KEY_DEMO:', self.transformed)


if __name__ == "__main__":
    unittest.main()
