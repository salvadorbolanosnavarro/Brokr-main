"""Permanent regression guard for WhatsApp 2 config/auth migration."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WhatsAppConfigAuthRegressionTests(unittest.TestCase):
    def test_router_uses_core_config_and_auth(self):
        source = (ROOT / "whatsapp.py").read_text(encoding="utf-8")
        access_source = (ROOT / "routers" / "whatsapp_access.py").read_text(encoding="utf-8")
        media_source = (ROOT / "routers" / "whatsapp_media_storage.py").read_text(encoding="utf-8")

        access_import = "from routers.whatsapp_access import _ids_visibles, _require_user"
        legacy_helper = 'return await require_user_id(request, detail="No autorizado")'
        access_extracted = access_import in source
        media_import = (
            "from routers.whatsapp_media_storage import "
            "borrar_archivos as _borrar_archivos, guardar_archivo as _guardar_archivo"
        )
        media_extracted = media_import in source

        self.assertIn("from core.config import settings", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("async def get_user_id_from_token", source)
        self.assertNotIn("or SUPABASE_ANON_KEY", source)
        self.assertNotIn("SUPABASE_SERVICE_KEY", source)
        self.assertIn("WA2_MODEL         = settings.wa2_model", source)
        self.assertIn("META_APP_ID     = settings.wa2_meta_app_id", source)
        self.assertIn("WA2_VERIFY_TOKEN = settings.wa2_verify_token", source)
        self.assertIn("WA2_APP_SECRET   = settings.wa2_app_secret", source)
        self.assertIn("WA2_DEBOUNCE = settings.wa2_debounce_seconds", source)
        self.assertIn("WA2_CAMPANA_TOPE = settings.wa2_campaign_limit", source)
        self.assertIn("WA2_TOPE_IA = settings.wa2_ai_limit", source)

        if access_extracted:
            self.assertNotIn("async def _require_user(", source)
            self.assertNotIn("async def _ids_visibles(", source)
            self.assertIn("from core.auth import require_user_id", access_source)
            self.assertIn(legacy_helper, access_source)
        else:
            self.assertIn("from core.auth import require_user_id", source)
            self.assertIn(legacy_helper, source)

        self.assertIn("from core.database import delete_rows, get_rows, patch_rows, post_rows", source)
        if media_extracted:
            self.assertNotIn("async def _guardar_archivo(", source)
            self.assertNotIn("async def _borrar_archivos(", source)
            self.assertNotIn("from core.storage import delete_objects, upload_object", source)
            self.assertIn("from core.storage import delete_objects, upload_object", media_source)
        else:
            self.assertIn("from core.storage import delete_objects, upload_object", source)

        compile(source, "whatsapp.py", "exec")
        compile(access_source, "routers/whatsapp_access.py", "exec")
        compile(media_source, "routers/whatsapp_media_storage.py", "exec")


if __name__ == "__main__":
    unittest.main()
