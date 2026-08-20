"""Permanent guard for EasyBroker stats new-contact batch POST Core routing."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "easybroker_import_stats.py"


class MainEbStatsContactBatchPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_contact_batch_post_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('await post_rows("contactos", chunk', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('/rest/v1/contactos', block)

    def test_success_ids_and_http_failure_behavior_are_preserved(self):
        block = self.block
        self.assertIn('creados += len(chunk)', block)
        self.assertIn('ids_creados_ok.update(c["id"] for c in chunk)', block)
        self.assertIn('except httpx.HTTPStatusError:\n                errores += len(chunk)', block)
        self.assertIn('await patch_rows("contactos", {"id": f"in.({lista})"}', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('await post_rows("contactos_propiedades", chunk', block)
        self.assertIn('except httpx.HTTPStatusError:\n                pass', block)
        self.assertNotIn('/rest/v1/contactos_propiedades', block)


if __name__ == "__main__":
    unittest.main()
