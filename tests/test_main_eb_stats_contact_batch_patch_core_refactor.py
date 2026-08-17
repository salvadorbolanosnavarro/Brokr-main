"""Permanent guard for EasyBroker stats existing-contact batch PATCH Core routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainEbStatsContactBatchPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/easybroker/import-stats")')
        end = cls.source.index('\n\n# ─────────────────────────────────────────────\n# ADMIN', start)
        cls.block = cls.source[start:end]

    def test_existing_contact_batch_patch_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('await patch_rows(\n                    "contactos",', block)
        self.assertIn('{"id": f"in.({lista})"}', block)
        self.assertIn('{"es_potencial": True, "updated_at": ahora}', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertNotIn('rp = await client.patch(\n                f"{SUPABASE_URL}/rest/v1/contactos"', block)

    def test_marked_and_http_failure_counters_are_preserved(self):
        block = self.block
        self.assertIn('marcados += len(lote)', block)
        self.assertIn('except httpx.HTTPStatusError:\n                errores += len(lote)', block)
        self.assertIn('await post_rows(\n                    "contactos_propiedades",', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertIn('except httpx.HTTPStatusError:\n                pass', block)
        self.assertNotIn('rv = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)


if __name__ == "__main__":
    unittest.main()
