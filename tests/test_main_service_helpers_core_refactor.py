"""Permanent guards for legacy _sb_service_* adapters routed through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainServiceHelpersCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        g0 = cls.source.index("async def _sb_service_get")
        g1 = cls.source.index("async def _sb_service_patch", g0)
        g2 = cls.source.index("async def _exigir_admin_de_org", g1)
        cls.get_block = cls.source[g0:g1]
        cls.patch_block = cls.source[g1:g2]

    def test_get_adapter_preserves_exact_200_json_fail_soft_contract(self):
        block = self.get_block
        self.assertIn('return await get_service_json(', block)
        self.assertIn('accepted_statuses=(200,)', block)
        self.assertIn('timeout=10', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('except json.JSONDecodeError:', block)
        self.assertNotIn('except Exception:', block)
        self.assertNotIn('/rest/v1/', block)

    def test_patch_adapter_preserves_http_ignore_transport_propagation(self):
        block = self.patch_block
        self.assertIn('await patch_rows_no_response(', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=10', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertNotIn('except Exception:', block)
        self.assertNotIn('/rest/v1/', block)

    def test_core_raw_primitives_are_imported(self):
        self.assertIn('get_service_json', self.source.split('\n', 12)[6])
        self.assertIn('patch_rows_no_response', self.source.split('\n', 12)[6])


if __name__ == "__main__":
    unittest.main()
