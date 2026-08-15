"""Permanent regression guard for Finanzas private Storage migration."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinanzasStorageRegressionTests(unittest.TestCase):
    def test_router_uses_canonical_storage(self):
        source = (ROOT / "routers" / "finanzas.py").read_text(encoding="utf-8")

        self.assertIn(
            "from core.storage import create_signed_object_url, delete_object, upload_object",
            source,
        )
        self.assertNotIn("service_headers", source)
        self.assertNotIn("def _headers(", source)
        self.assertNotIn("/storage/v1/object/", source)
        self.assertNotIn("SUPABASE_URL =", source)
        self.assertNotIn("SUPABASE_SERVICE_KEY =", source)
        self.assertIn("await delete_object(BUCKET, ruta, timeout=20)", source)
        self.assertIn("await upload_object(", source)
        self.assertIn("await create_signed_object_url(", source)
        # Anthropic ticket extraction remains domain-local by design; PDF
        # colors are now canonical too.
        self.assertIn("https://api.anthropic.com/v1/messages", source)
        self.assertIn("_PDF_TOKENS = pdf_palette()", source)
        compile(source, "routers/finanzas.py", "exec")


if __name__ == "__main__":
    unittest.main()
