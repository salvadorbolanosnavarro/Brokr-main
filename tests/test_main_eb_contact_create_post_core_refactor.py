"""Permanent guard for /contactos/importar-eb new-contact POST Core routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "easybroker_contact_import.py"


class MainEbContactCreatePostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_new_contact_post_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('await post_rows(\n                        "contactos",', block)
        self.assertIn('nuevo,', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=20', block)
        self.assertIn('accepted_statuses=(200, 201)', block)
        self.assertNotIn('ri = await client.post(', block)
        self.assertNotIn('/rest/v1/contactos', block)

    def test_counter_and_dedup_cache_contract_are_preserved(self):
        block = self.block
        self.assertIn('importados += 1', block)
        self.assertIn('if m["telefono"]:\n                        existing_by_tel[m["telefono"]] = nuevo', block)
        self.assertIn('if m["email"]:\n                        existing_by_email[m["email"]] = nuevo', block)
        self.assertIn('except httpx.HTTPStatusError:\n                    errores += 1', block)


if __name__ == "__main__":
    unittest.main()
