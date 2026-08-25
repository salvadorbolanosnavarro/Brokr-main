"""Permanent guards for shared Facebook persistence compatibility helpers."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_persistence.py"
PROCESSOR = ROOT / "core" / "facebook_leadgen_processor.py"


class FacebookPersistenceCoreExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")
        cls.processor = PROCESSOR.read_text(encoding="utf-8")

    def test_main_delegates_persistence_compatibility_helpers_to_core(self):
        self.assertIn("from core.facebook_persistence import (", self.main)
        self.assertIn("FACEBOOK_AD_ENTITIES_TABLE as _FB_TABLA_ENTIDADES", self.main)
        self.assertIn("facebook_table_missing as _fb_tabla_falta", self.main)
        self.assertIn("warn_facebook_migration as _fb_avisa_migracion", self.main)
        self.assertIn("reserve_facebook_creation as _fb_reservar_creacion", self.main)
        self.assertIn("find_facebook_creation_by_idempotency as _fb_buscar_por_idempotencia", self.main)
        self.assertIn("update_facebook_entity as _fb_actualizar_entidad", self.main)
        self.assertNotIn('_FB_TABLA_ENTIDADES = "fb_ad_entities"', self.main)
        self.assertNotIn("_fb_aviso_tabla_dado = False", self.main)
        self.assertNotIn("def _fb_tabla_falta(", self.main)
        self.assertNotIn("def _fb_avisa_migracion(", self.main)
        self.assertNotIn("async def _fb_reservar_creacion(", self.main)
        self.assertNotIn("async def _fb_buscar_por_idempotencia(", self.main)
        self.assertNotIn("async def _fb_actualizar_entidad(", self.main)

    def test_core_preserves_missing_table_detection_exactly(self):
        core = self.core
        self.assertIn('FACEBOOK_AD_ENTITIES_TABLE = "fb_ad_entities"', core)
        self.assertIn("if response.status_code not in (404, 400):", core)
        self.assertIn('"does not exist" in text', core)
        self.assertIn('"could not find the table" in text', core)
        self.assertIn('"pgrst205" in text', core)

    def test_core_preserves_one_time_legacy_warning(self):
        core = self.core
        self.assertIn("_migration_warning_emitted = False", core)
        self.assertIn("global _migration_warning_emitted", core)
        self.assertIn("if not _migration_warning_emitted:", core)
        self.assertIn("migracion-facebook-ads.sql", core)
        self.assertIn("Los anuncios se siguen creando sin ella.", core)
        self.assertIn("_migration_warning_emitted = True", core)
        self.assertNotIn("from main import", core)

    def test_existing_consumers_follow_shared_persistence_core(self):
        core = self.core
        processor = self.processor
        self.assertIn("rows = await post_rows(", core)
        self.assertIn("FACEBOOK_AD_ENTITIES_TABLE,", core)
        self.assertIn("if facebook_table_missing(response):", core)
        self.assertIn('warn_facebook_migration("reservar creación", response)', core)
        self.assertIn("facebook_table_missing(exc.response)", processor)
        self.assertIn('warn_facebook_migration("procesar lead", exc.response)', processor)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/facebook_persistence.py", "exec")
        compile(self.processor, "core/facebook_leadgen_processor.py", "exec")


if __name__ == "__main__":
    unittest.main()
