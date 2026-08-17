"""Dry-run guard for EasyBroker bulk property upsert Core routing."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_property_bulk_upsert_core.py"

spec = importlib.util.spec_from_file_location("property_bulk_upsert_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainPropertyBulkUpsertTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.transformed = transform.transform_source(cls.source)

    def test_transform_is_exact_idempotent_and_compiles(self):
        compile(self.transformed, "main.py", "exec")
        self.assertEqual(MAIN.read_text(encoding="utf-8"), self.source)
        self.assertEqual(self.transformed.count(transform.NEW_IMPORT), 1)
        self.assertEqual(self.transformed.count(transform.NEW), 1)
        self.assertNotIn(transform.OLD, self.transformed)
        if transform.OLD in self.source:
            expected = self.source.replace(transform.OLD_IMPORT, transform.NEW_IMPORT, 1).replace(transform.OLD, transform.NEW, 1)
            self.assertEqual(self.transformed, expected)
        else:
            self.assertEqual(self.transformed, self.source)

    def test_retry_status_text_and_counter_contract_are_preserved(self):
        new = transform.NEW
        self.assertIn('for intento in range(3):', new)
        self.assertIn('await upsert_rows(', new)
        self.assertIn('"propiedades"', new)
        self.assertIn('chunk,', new)
        self.assertIn('conflict="org_id,eb_public_id"', new)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', new)
        self.assertIn('timeout=60', new)
        self.assertIn('accepted_statuses=(200, 201, 204)', new)
        self.assertIn('upserted += len(chunk)', new)
        self.assertIn('guardado = True', new)
        self.assertIn('break', new)
        self.assertIn('except httpx.HTTPStatusError as e:', new)
        self.assertIn('ultimo_fallo = f"Supabase {e.response.status_code}: {e.response.text[:200]}"', new)
        self.assertIn('except Exception as e:', new)
        self.assertIn('ultimo_fallo = str(e)[:200]', new)
        self.assertIn('await asyncio.sleep(1.5 * (2 ** intento))', new)
        self.assertIn('if not guardado:', new)
        self.assertIn('"id": f"lote_{i // UPSERT_BATCH}"', new)
        self.assertNotIn('/rest/v1/', new)


if __name__ == "__main__":
    unittest.main()
