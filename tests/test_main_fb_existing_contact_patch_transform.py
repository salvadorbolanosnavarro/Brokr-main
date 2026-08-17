"""Dry-run guard for Facebook lead existing-contact PATCH Core migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_fb_existing_contact_patch_core.py"

spec = importlib.util.spec_from_file_location("fb_existing_contact_patch_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainFbExistingContactPatchTransformTests(unittest.TestCase):
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

    def test_http_and_transport_semantics_are_preserved(self):
        new = transform.NEW
        self.assertIn('await patch_rows(', new)
        self.assertIn('"contactos"', new)
        self.assertIn('{"id": f"eq.{existente[\'id\']}"}', new)
        self.assertIn('{"es_potencial": True, "updated_at": ahora}', new)
        self.assertIn('timeout=15', new)
        self.assertIn('except httpx.HTTPStatusError:', new)
        self.assertNotIn('except Exception', new)
        self.assertNotIn('/rest/v1/', new)

    def test_downstream_success_annotation_is_untouched(self):
        marker = 'await _anota({"procesado": True, "contacto_id": existente["id"],'
        self.assertIn(marker, self.transformed)
        self.assertIn('Contacto ya existía; se marcó como potencial.', self.transformed)
        self.assertIn('Lead %s emparejado con el contacto %s', self.transformed)


if __name__ == "__main__":
    unittest.main()
