"""Permanent guard for manual photo-migration property PATCH Core routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainManualPhotoPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/easybroker/migrar-fotos")')
        end = cls.source.index("\n\n@app.", start + 10)
        cls.block = cls.source[start:end]

    def test_property_photo_patch_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('await patch_rows(\n                    "propiedades",', block)
        self.assertIn('{"id": f"eq.{pid}"}', block)
        self.assertIn('{"fotos": nuevas}', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertNotIn('await client.patch(\n                    f"{SUPABASE_URL}/rest/v1/propiedades"', block)

    def test_success_and_failure_counters_are_preserved(self):
        block = self.block
        self.assertIn('propiedades_ok += 1', block)
        self.assertIn('fotos_subidas += subidas_prop', block)
        self.assertIn('except Exception:\n                errores += 1', block)
        self.assertIn('"propiedades_actualizadas": propiedades_ok', block)
        self.assertIn('"fotos_subidas":            fotos_subidas', block)
        self.assertIn('"errores":                  errores', block)


if __name__ == "__main__":
    unittest.main()
