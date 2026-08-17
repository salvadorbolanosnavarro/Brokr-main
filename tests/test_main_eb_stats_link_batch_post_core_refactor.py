"""Permanent guard for EasyBroker stats contact-property batch POST Core routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainEbStatsLinkBatchPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/easybroker/import-stats")')
        end = cls.source.index('\n\n# ─────────────────────────────────────────────\n# ADMIN', start)
        cls.block = cls.source[start:end]

    def test_link_batch_post_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('await post_rows(\n                    "contactos_propiedades",', block)
        self.assertIn('chunk,', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('rv = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)

    def test_filter_counter_and_http_fail_soft_behavior_are_preserved(self):
        block = self.block
        self.assertIn('vinculos_validos = [v for v in vinculos_lote', block)
        self.assertIn('if v["contacto_id"] in ids_creados_ok', block)
        self.assertIn('or v["contacto_id"] not in ids_nuevos_todos', block)
        self.assertIn('vinculos_nuevos += len(chunk)', block)
        self.assertIn('except httpx.HTTPStatusError:\n                pass', block)


if __name__ == "__main__":
    unittest.main()
