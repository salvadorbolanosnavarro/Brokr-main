"""Permanent guards for the Firmas Core database/Storage migration."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FirmasDatabaseStorageRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "routers/firmas.py").read_text(encoding="utf-8")

    def test_firmas_delegates_database_and_storage_to_core(self):
        source = self.source
        self.assertIn(
            "from core.database import delete_rows, get_rows, patch_rows, post_rows",
            source,
        )
        self.assertIn(
            "from core.storage import create_signed_object_url, delete_object, download_object, upload_object",
            source,
        )
        self.assertNotIn("/rest/v1/", source)
        self.assertNotIn("/storage/v1/object/", source)
        self.assertNotIn("def _headers(", source)
        self.assertIn("return await get_rows(", source)
        self.assertIn("return await post_rows(", source)
        self.assertIn("return await patch_rows(", source)
        self.assertIn("await delete_rows(", source)
        self.assertIn("await upload_object(", source)
        self.assertIn("return await download_object(", source)
        self.assertIn("return await create_signed_object_url(", source)
        self.assertIn("await delete_object(", source)

    def test_legal_signature_invariants_remain_explicit(self):
        source = self.source
        self.assertIn("El PDF original no se modifica NUNCA", source)
        self.assertIn("CONSENTIMIENTO = (", source)
        self.assertIn(
            "def _sha256(b: bytes) -> str:\n    return hashlib.sha256(b).hexdigest()",
            source,
        )
        self.assertIn("async def evento", source)
        self.assertIn(
            'except Exception as e:\n        log.warning("evento falló',
            source,
        )
        compile(source, "routers/firmas.py", "exec")


if __name__ == "__main__":
    unittest.main()
