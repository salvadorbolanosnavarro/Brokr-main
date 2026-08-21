from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from routers.whatsapp_media_storage import borrar_archivos, guardar_archivo
from scripts.refactor_whatsapp_extract_media_storage_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"


class WhatsAppMediaStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_media_is_not_uploaded(self):
        with patch("routers.whatsapp_media_storage.upload_object", new=AsyncMock()) as upload:
            self.assertEqual(await guardar_archivo("u1", "c1", b"", "image/jpeg", "foto"), (None, None))
            upload.assert_not_awaited()

    async def test_upload_delegates_to_core_storage_and_returns_path(self):
        with patch(
            "routers.whatsapp_media_storage.upload_object",
            new=AsyncMock(return_value="https://public.test/media.jpg"),
        ) as upload:
            url, path = await guardar_archivo("u1", "c1", b"abc", "image/jpeg", "foto")
        self.assertEqual(url, "https://public.test/media.jpg")
        self.assertTrue(path.startswith("u1/c1/"))
        self.assertTrue(path.endswith("-foto.jpeg"))
        upload.assert_awaited_once()

    async def test_delete_filters_empty_paths_and_is_fail_soft(self):
        with patch("routers.whatsapp_media_storage.delete_objects", new=AsyncMock()) as delete:
            await borrar_archivos([None, "", "u1/c1/a.jpg"])
            args = delete.await_args.args
            self.assertEqual(args[1], ["u1/c1/a.jpg"])
        with patch(
            "routers.whatsapp_media_storage.delete_objects",
            new=AsyncMock(side_effect=RuntimeError("storage down")),
        ):
            await borrar_archivos(["u1/c1/a.jpg"])


class WhatsAppMediaStorageExtractionTests(unittest.TestCase):
    def test_transform_moves_only_storage_helpers(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("borrar_archivos as _borrar_archivos", transformed)
        self.assertIn("guardar_archivo as _guardar_archivo", transformed)
        self.assertNotIn("async def _guardar_archivo", transformed)
        self.assertNotIn("async def _borrar_archivos", transformed)
        self.assertIn("async def _descargar_media", transformed)
        self.assertIn("async def _transcribir_audio", transformed)
        self.assertIn("async def wa2_borrar_mensaje", transformed)
        self.assertIn("async def wa2_borrar_conversacion", transformed)
        self.assertIn("async def wa2_numero_delete", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
