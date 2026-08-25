"""Permanent guards for Facebook Ads creation persistence living in Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_persistence.py"


class FacebookAdsPersistenceExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_main_delegates_creation_persistence_to_core(self):
        self.assertNotIn("async def _fb_reservar_creacion(", self.main)
        self.assertNotIn("async def _fb_buscar_por_idempotencia(", self.main)
        self.assertNotIn("async def _fb_actualizar_entidad(", self.main)
        self.assertIn("reserve_facebook_creation as _fb_reservar_creacion", self.main)
        self.assertIn("find_facebook_creation_by_idempotency as _fb_buscar_por_idempotencia", self.main)
        self.assertIn("update_facebook_entity as _fb_actualizar_entidad", self.main)

    def test_core_preserves_idempotency_and_fail_soft_contract(self):
        core = self.core
        self.assertIn('FACEBOOK_AD_ENTITIES_TABLE = "fb_ad_entities"', core)
        self.assertIn('"status": "CREANDO"', core)
        self.assertIn('prefer="return=representation"', core)
        self.assertIn('accepted_statuses=(200, 201)', core)
        self.assertIn('response.status_code == 409 and idempotency_key', core)
        self.assertIn('return {"modo": "duplicado", "row": previous}', core)
        self.assertIn('return {"modo": "sin_tabla"}', core)
        self.assertIn('"updated_at": datetime.now(timezone.utc).isoformat()', core)
        self.assertIn('warn_facebook_migration("actualizar entidad", exc.response)', core)
        self.assertIn('except Exception as exc:', core)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/facebook_persistence.py", "exec")


if __name__ == "__main__":
    unittest.main()
