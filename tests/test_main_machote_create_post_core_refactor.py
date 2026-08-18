"""Permanent guard for machote creation POST Core routing."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "machotes.py"


class MainMachoteCreatePostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")
        start = cls.source.index('@router.post("/contrato/machote/crear")')
        end = cls.source.index('\n\n@router.get("/contrato/machotes")', start)
        cls.block = cls.source[start:end]

    def test_create_post_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('await post_rows(', block)
        self.assertIn('"machotes_contrato"', block)
        self.assertIn('fila,', block)
        self.assertIn('prefer="return=representation"', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200, 201)', block)
        self.assertNotIn('/rest/v1/machotes_contrato', block)

    def test_http_cleanup_and_transport_behavior_are_preserved(self):
        block = self.block
        self.assertIn('except httpx.HTTPStatusError as e:', block)
        self.assertIn('for p in (storage_path, storage_path_original):', block)
        self.assertIn('/storage/v1/object/{MACHOTES_BUCKET}/{p}', block)
        self.assertIn('e.response.text[:200]', block)
        segment = block[block.index('await post_rows('):]
        self.assertNotIn('except Exception as e:', segment)


if __name__ == "__main__":
    unittest.main()
