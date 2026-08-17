"""Dry-run guard for the website-lead contact dedup GET Core migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_website_lead_contact_read_core.py"

spec = importlib.util.spec_from_file_location("website_lead_contact_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainWebsiteLeadContactReadTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.transformed = transform.transform_source(cls.source)

    def test_transform_is_bounded_and_compiles(self):
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

    def test_legacy_http_rejection_remains_no_match(self):
        self.assertIn("except httpx.HTTPStatusError:\n                filas = []", transform.NEW)
        self.assertNotIn("except Exception", transform.NEW)
        self.assertIn("existente = filas[0] if filas else None", transform.NEW)
        self.assertIn('"user_id": f"eq.{user_id}"', transform.NEW)
        self.assertIn('"telefono": f"eq.{telefono}"', transform.NEW)
        self.assertIn('"select": "id,notas,es_potencial"', transform.NEW)
        self.assertIn('"limit": "1"', transform.NEW)
        self.assertIn("timeout=10", transform.NEW)


if __name__ == "__main__":
    unittest.main()
