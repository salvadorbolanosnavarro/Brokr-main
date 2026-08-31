"""Permanent regression guard for WhatsApp 2 Storage migration."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WhatsAppStorageRegressionTests(unittest.TestCase):
    def test_router_routes_storage_through_core(self):
        source = (ROOT / "whatsapp.py").read_text(encoding="utf-8")
        media_source = (ROOT / "routers" / "whatsapp_media_storage.py").read_text(
            encoding="utf-8"
        )
        media_import = (
            "from routers.whatsapp_media_storage import "
            "borrar_archivos as _borrar_archivos, guardar_archivo as _guardar_archivo"
        )
        media_extracted = media_import in source
        storage_source = media_source if media_extracted else source

        self.assertIn(
            "from core.storage import delete_objects, upload_object",
            storage_source,
        )
        self.assertIn("await upload_object(", storage_source)
        self.assertIn(
            "await delete_objects(WA_MEDIA_BUCKET, rutas, timeout=20)",
            storage_source,
        )
        if media_extracted:
            self.assertNotIn(
                "from core.storage import delete_objects, upload_object",
                source,
            )
            self.assertNotIn("async def _guardar_archivo(", source)
            self.assertNotIn("async def _borrar_archivos(", source)

        self.assertNotIn("service_headers", source)
        self.assertNotIn("def _sb_headers()", source)
        self.assertNotIn("SUPABASE_URL", source)
        self.assertNotIn("SUPABASE_ANON_KEY", source)
        self.assertNotIn("SUPABASE_SERVICE_KEY", source)
        self.assertNotIn("/storage/v1/object/", storage_source)
        # Meta media download and AI clients remain external HTTP by design.
        self.assertIn("async def _descargar_media", source)
        self.assertIn("GRAPH_API", source)
        self.assertIn("ANTHROPIC_BASE", source)
        self.assertIn("GROQ_BASE", source)
        compile(source, "whatsapp.py", "exec")
        compile(media_source, "routers/whatsapp_media_storage.py", "exec")


if __name__ == "__main__":
    unittest.main()
