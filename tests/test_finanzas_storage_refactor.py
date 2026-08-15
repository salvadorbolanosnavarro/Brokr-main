"""Dry-run the Finanzas Storage migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_finanzas_storage import transform

ROOT = Path(__file__).resolve().parents[1]


class FinanzasStorageRefactorTests(unittest.TestCase):
    def test_transform_matches_current_source_and_compiles(self):
        source = (ROOT / "routers" / "finanzas.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn(
            "from core.storage import create_signed_object_url, delete_object, upload_object",
            updated,
        )
        self.assertNotIn("service_headers", updated)
        self.assertNotIn("def _headers(", updated)
        self.assertNotIn("/storage/v1/object/", updated)
        self.assertNotIn("SUPABASE_URL =", updated)
        self.assertNotIn("SUPABASE_SERVICE_KEY =", updated)
        self.assertIn("await delete_object(BUCKET, ruta, timeout=20)", updated)
        self.assertIn("await upload_object(", updated)
        self.assertIn("await create_signed_object_url(", updated)
        # Anthropic ticket extraction and PDF design are separate cuts.
        self.assertIn("https://api.anthropic.com/v1/messages", updated)
        self.assertIn("_PDF_TOKENS = {", updated)
        compile(updated, "routers/finanzas.py", "exec")


if __name__ == "__main__":
    unittest.main()
