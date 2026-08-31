"""Permanent guards for service-role legacy policies after local adapter removal."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainServiceHelpersCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_local_legacy_adapters_stay_removed(self):
        self.assertNotIn('async def _sb_service_get', self.source)
        self.assertNotIn('async def _sb_service_patch', self.source)
        self.assertNotIn('_sb_service_get(', self.source)
        self.assertNotIn('_sb_service_patch(', self.source)

    def test_named_core_policies_are_imported(self):
        tree = ast.parse(self.source)
        imports = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "core.database"
            for alias in node.names
        }
        self.assertIn('get_service_json_or_empty', imports)
        self.assertIn('patch_rows_ignoring_http_status', imports)
        self.assertIn('get_service_json', imports)
        self.assertIn('patch_rows_no_response', imports)

    def test_main_remains_free_of_direct_postgrest(self):
        self.assertNotIn('/rest/v1/', self.source)


if __name__ == "__main__":
    unittest.main()
