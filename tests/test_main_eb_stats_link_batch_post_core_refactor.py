"""Permanent guard for EasyBroker stats contact-property batch POST Core routing."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "easybroker_import_stats.py"


class MainEbStatsLinkBatchPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_link_batch_post_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('await post_rows("contactos_propiedades", chunk', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('/rest/v1/contactos_propiedades', block)

    def test_filter_counter_and_http_fail_soft_behavior_are_preserved(self):
        block = self.block
        self.assertIn('vinculos_validos = [v for v in vinculos_lote', block)
        self.assertIn('if v["contacto_id"] in ids_creados_ok or v["contacto_id"] not in ids_nuevos_todos', block)
        self.assertIn('vinculos_nuevos += len(chunk)', block)
        self.assertIn('except httpx.HTTPStatusError:\n                pass', block)


if __name__ == "__main__":
    unittest.main()
