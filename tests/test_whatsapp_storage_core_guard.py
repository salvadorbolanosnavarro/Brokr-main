from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
CORE_STORAGE = ROOT / "core" / "storage.py"


class WhatsAppStorageCoreGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WHATSAPP.read_text(encoding="utf-8")
        cls.core = CORE_STORAGE.read_text(encoding="utf-8")

    def test_media_upload_delegates_to_core_storage(self):
        self.assertIn("from core.storage import delete_objects, upload_object", self.source)
        self.assertIn("url = await upload_object(", self.source)
        self.assertIn("WA_MEDIA_BUCKET", self.source)
        self.assertIn('content_type=mime or "application/octet-stream"', self.source)
        self.assertIn("timeout=40", self.source)

    def test_media_delete_delegates_to_core_storage(self):
        self.assertIn("await delete_objects(WA_MEDIA_BUCKET, rutas, timeout=20)", self.source)
        self.assertNotIn('f"{settings.supabase_url}/storage/v1/object/{WA_MEDIA_BUCKET}', self.source)

    def test_core_storage_keeps_path_traversal_guards(self):
        self.assertIn('if any(part in ("", ".", "..")', self.core)
        self.assertIn("_normalize_object_path(path)", self.core)
        self.assertIn("_require_bucket(bucket)", self.core)


if __name__ == "__main__":
    unittest.main()
