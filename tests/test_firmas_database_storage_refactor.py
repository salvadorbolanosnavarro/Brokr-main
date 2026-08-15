"""Dry-run guard for the Firmas database/Storage Core migration."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_firmas_database_storage import transform


ROOT = Path(__file__).resolve().parents[1]


class FirmasDatabaseStorageRefactorTests(unittest.TestCase):
    def test_transform_preserves_legal_invariants_and_compiles(self):
        source = (ROOT / "routers/firmas.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertNotEqual(source, updated)
        self.assertNotIn("/rest/v1/", updated)
        self.assertNotIn("/storage/v1/object/", updated)
        self.assertIn("from core.database import delete_rows, get_rows, patch_rows, post_rows", updated)
        self.assertIn("from core.storage import create_signed_object_url, delete_object, download_object, upload_object", updated)
        self.assertIn("El PDF original no se modifica NUNCA", updated)
        self.assertIn("def _sha256(b: bytes) -> str:", updated)
        self.assertIn("CONSENTIMIENTO = (", updated)
        self.assertIn("async def evento", updated)
        self.assertIn("except Exception as e:\n        log.warning(\"evento falló", updated)
        compile(updated, "routers/firmas.py", "exec")


if __name__ == "__main__":
    unittest.main()
