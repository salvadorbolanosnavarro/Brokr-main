from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
MEDIA_STORAGE = ROOT / "routers" / "whatsapp_media_storage.py"
CORE_STORAGE = ROOT / "core" / "storage.py"


class WhatsAppStorageCoreGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WHATSAPP.read_text(encoding="utf-8")
        cls.media = MEDIA_STORAGE.read_text(encoding="utf-8")
        cls.core = CORE_STORAGE.read_text(encoding="utf-8")
        cls.media_import = (
            "from routers.whatsapp_media_storage import "
            "borrar_archivos as _borrar_archivos, guardar_archivo as _guardar_archivo"
        )
        cls.media_extracted = cls.media_import in cls.source
        cls.storage_source = cls.media if cls.media_extracted else cls.source

    def test_media_upload_delegates_to_core_storage(self):
        self.assertIn(
            "from core.storage import delete_objects, upload_object",
            self.storage_source,
        )
        self.assertIn("url = await upload_object(", self.storage_source)
        self.assertIn("WA_MEDIA_BUCKET", self.storage_source)
        self.assertIn(
            'content_type=mime or "application/octet-stream"',
            self.storage_source,
        )
        self.assertIn("timeout=40", self.storage_source)
        if self.media_extracted:
            self.assertNotIn(
                "from core.storage import delete_objects, upload_object",
                self.source,
            )

    def test_media_delete_delegates_to_core_storage(self):
        self.assertIn(
            "await delete_objects(WA_MEDIA_BUCKET, rutas, timeout=20)",
            self.storage_source,
        )
        self.assertNotIn(
            f'"{{settings.supabase_url}}/storage/v1/object/{{WA_MEDIA_BUCKET}}',
            self.storage_source,
        )

    def test_core_storage_keeps_path_traversal_guards(self):
        self.assertIn('if any(part in ("", ".", "..")', self.core)
        self.assertIn("_normalize_object_path(path)", self.core)
        self.assertIn("_require_bucket(bucket)", self.core)


if __name__ == "__main__":
    unittest.main()
