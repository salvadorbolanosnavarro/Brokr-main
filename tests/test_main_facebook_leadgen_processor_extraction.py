"""Permanent guards for Facebook Lead Ads processing living outside main.py."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_leadgen_processor.py"


class FacebookLeadgenProcessorExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_main_keeps_webhook_but_delegates_processing_to_core(self):
        main = self.main
        self.assertIn("from core.facebook_leadgen_processor import (", main)
        self.assertIn("FACEBOOK_LEAD_FIELDS as _FB_CAMPOS_LEAD", main)
        self.assertIn("find_facebook_page_owner as _fb_buscar_dueno_de_pagina", main)
        self.assertIn("process_facebook_lead as _fb_procesar_lead", main)
        self.assertIn('@app.post("/facebook/leadgen/webhook")', main)
        self.assertIn("background.add_task(_fb_procesar_lead, valor)", main)
        self.assertNotIn("async def _fb_buscar_dueno_de_pagina(", main)
        self.assertNotIn("async def _fb_procesar_lead(", main)
        self.assertNotIn("_FB_CAMPOS_LEAD = {", main)

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


if __name__ == "__main__":
    unittest.main()
