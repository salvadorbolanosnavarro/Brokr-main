"""Permanent guard for EasyBroker stats new-contact batch POST Core routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainEbStatsContactBatchPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/easybroker/import-stats")')
        end = cls.source.index('\n\n# ─────────────────────────────────────────────\n# ADMIN', start)
        cls.block = cls.source[start:end]

    def test_contact_batch_post_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('await post_rows(\n                    "contactos",', block)
        self.assertIn('chunk,', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('ri = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos"', block)

    def test_success_ids_and_http_failure_behavior_are_preserved(self):
        block = self.block
        self.assertIn('creados += len(chunk)', block)
        self.assertIn('ids_creados_ok.update(c["id"] for c in chunk)', block)
        self.assertIn('except httpx.HTTPStatusError:\n                errores += len(chunk)', block)
        self.assertIn('rp = await client.patch(\n                f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('rv = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)


if __name__ == "__main__":
    unittest.main()
