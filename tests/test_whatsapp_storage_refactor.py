"""Dry-run WhatsApp 2 Storage migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_whatsapp_storage import transform

ROOT = Path(__file__).resolve().parents[1]


class WhatsAppStorageRefactorTests(unittest.TestCase):
    def test_transform_routes_storage_through_core_and_compiles(self):
        source = (ROOT / "whatsapp.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.storage import delete_objects, upload_object", updated)
        self.assertIn("await upload_object(", updated)
        self.assertIn("await delete_objects(WA_MEDIA_BUCKET, rutas, timeout=20)", updated)
        self.assertNotIn("service_headers", updated)
        self.assertNotIn("def _sb_headers()", updated)
        self.assertNotIn("SUPABASE_URL", updated)
        self.assertNotIn("SUPABASE_ANON_KEY", updated)
        self.assertNotIn("SUPABASE_SERVICE_KEY", updated)
        self.assertNotIn("/storage/v1/object/", updated)
        # Meta media download and AI clients remain external HTTP by design.
        self.assertIn("async def _descargar_media", updated)
        self.assertIn("GRAPH_API", updated)
        self.assertIn("ANTHROPIC_BASE", updated)
        self.assertIn("GROQ_BASE", updated)
        compile(updated, "whatsapp.py", "exec")


if __name__ == "__main__":
    unittest.main()
