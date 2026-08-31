"""Permanent guards for Facebook Lead Ads processing living outside main.py."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_leadgen_processor.py"
WEBHOOK_ROUTER = ROOT / "routers" / "facebook_leadgen_webhook.py"


class FacebookLeadgenProcessorExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")
        cls.webhook_router = WEBHOOK_ROUTER.read_text(encoding="utf-8")

    def test_main_delegates_processor_and_post_webhook_outside_main(self):
        main = self.main
        self.assertIn("from core.facebook_leadgen_processor import (", main)
        self.assertIn("FACEBOOK_LEAD_FIELDS as _FB_CAMPOS_LEAD", main)
        self.assertIn("find_facebook_page_owner as _fb_buscar_dueno_de_pagina", main)
        self.assertIn("process_facebook_lead as _fb_procesar_lead", main)
        self.assertNotIn('@app.post("/facebook/leadgen/webhook")', main)
        self.assertNotIn("async def _fb_buscar_dueno_de_pagina(", main)
        self.assertNotIn("async def _fb_procesar_lead(", main)
        self.assertNotIn("_FB_CAMPOS_LEAD = {", main)

    def test_webhook_router_delegates_background_processing_to_core(self):
        router = self.webhook_router
        self.assertIn('from core.facebook_leadgen_processor import process_facebook_lead', router)
        self.assertIn('@router.post("/facebook/leadgen/webhook")', router)
        self.assertIn("background.add_task(process_facebook_lead, valor)", router)
        self.assertNotIn("from main import", router)

    def test_core_owns_page_owner_lookup_and_secret_decryption(self):
        core = self.core
        self.assertIn("async def find_facebook_page_owner(page_id: str) -> dict:", core)
        self.assertIn("if not page_id or not settings.supabase_url or not settings.supabase_service_key:", core)
        self.assertIn('"meta": f"like.*{page_id}*"', core)
        self.assertIn('"limit": "20"', core)
        self.assertIn('"limit": "500"', core)
        self.assertIn("decrypt_facebook_secret(row.get(\"api_key\", \"\"))", core)

    def test_core_preserves_lead_mapping_and_fail_soft_processing(self):
        core = self.core
        self.assertIn('FACEBOOK_LEAD_FIELDS = {', core)
        self.assertIn('"phone_number": "telefono"', core)
        self.assertIn("async def process_facebook_lead(value: dict) -> None:", core)
        self.assertIn('"fb_leads_recibidos"', core)
        self.assertIn('warn_facebook_migration("procesar lead", exc.response)', core)
        self.assertIn('async with httpx.AsyncClient(timeout=20) as client:', core)
        self.assertIn('"No se pudo leer el lead"', core)
        self.assertIn('"Facebook Lead Ads"', core)
        self.assertIn('["Facebook", "Lead Ad"]', core)
        self.assertIn('if org_id:', core)
        self.assertIn('elif email:', core)
        self.assertIn('"Contacto ya existía; se marcó como potencial."', core)
        self.assertNotIn("from main import", core)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/facebook_leadgen_processor.py", "exec")
        compile(self.webhook_router, "routers/facebook_leadgen_webhook.py", "exec")


if __name__ == "__main__":
    unittest.main()
