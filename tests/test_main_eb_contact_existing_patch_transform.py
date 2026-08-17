"""Dry-run guard for /contactos/importar-eb existing-contact PATCH Core routing."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_eb_contact_existing_patch_core.py"

spec = importlib.util.spec_from_file_location("eb_contact_existing_patch_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainEbContactExistingPatchTransformTests(unittest.TestCase):
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

    def test_filter_status_counters_and_transport_contract_are_preserved(self):
        new = transform.NEW
        self.assertIn('filtro_patch = ({"org_id": f"eq.{org_id_import}"} if org_id_import', new)
        self.assertIn('else {"user_id": f"eq.{user_id}"})', new)
        self.assertIn('await patch_rows(', new)
        self.assertIn('"contactos"', new)
        self.assertIn('{"id": f"eq.{existente[\'id\']}", **filtro_patch}', new)
        self.assertIn('patch,', new)
        self.assertIn('timeout=20', new)
        self.assertIn('accepted_statuses=(200, 204)', new)
        self.assertIn('actualizados += 1', new)
        self.assertIn('except httpx.HTTPStatusError:\n                        errores += 1', new)
        self.assertNotIn('except Exception', new)
        self.assertNotIn('/rest/v1/', new)


if __name__ == "__main__":
    unittest.main()
