"""Permanent guard: main.py delegates legacy service-role policies directly to Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainNoLegacyServiceAdaptersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_local_service_adapters_are_gone(self):
        self.assertNotIn('async def _sb_service_get(', self.source)
        self.assertNotIn('async def _sb_service_patch(', self.source)
        self.assertNotIn('_sb_service_get(', self.source)
        self.assertNotIn('_sb_service_patch(', self.source)

    def test_named_core_policies_are_used(self):
        self.assertIn('get_service_json_or_empty', self.source)
        self.assertIn('patch_rows_ignoring_http_status', self.source)
        self.assertGreaterEqual(self.source.count('get_service_json_or_empty('), 6)
        self.assertGreaterEqual(self.source.count('patch_rows_ignoring_http_status('), 4)

    def test_postgrest_implementation_remains_absent_from_main(self):
        self.assertNotIn('/rest/v1/', self.source)


if __name__ == '__main__':
    unittest.main()
