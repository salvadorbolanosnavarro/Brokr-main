from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "easybroker_migration.py"
CONTACT_ROUTER = ROOT / "routers" / "easybroker_contact_import.py"
MIGRATION_ROUTER = ROOT / "routers" / "easybroker_migration.py"


class EasyBrokerMigrationStateExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")
        cls.contact_router = CONTACT_ROUTER.read_text(encoding="utf-8")
        cls.migration_router = MIGRATION_ROUTER.read_text(encoding="utf-8")
        cls.legacy_owned = '@app.post("/easybroker/import-all")' in cls.main

    def test_shared_state_lives_in_core(self):
        self.assertIn('MIGRACIONES: dict = {}', self.core)
        self.assertIn('PROGRESO_IMPORT: dict = {}', self.core)
        self.assertNotIn('_MIGRACIONES: dict = {}', self.main)
        self.assertNotIn('_PROGRESO_IMPORT: dict = {}', self.main)
        self.assertNotIn('MIGRACIONES as _MIGRACIONES', self.main)
        self.assertNotIn('PROGRESO_IMPORT as _PROGRESO_IMPORT', self.main)
        self.assertIn('from core.easybroker_migration import MIGRACIONES, PROGRESO_IMPORT, migration_key', self.migration_router)

    def test_progress_and_key_contracts_are_preserved(self):
        c = self.core
        self.assertIn('def set_import_progress(user_id: str, texto: str)', c)
        self.assertIn('PROGRESO_IMPORT[user_id] = texto', c)
        self.assertIn('except Exception:\n        pass', c)
        self.assertIn('def migration_key(org_id, user_id):', c)
        self.assertIn('return f"org:{org_id}" if org_id else f"user:{user_id}"', c)
        self.assertIn('from core.easybroker_migration import set_import_progress as _prog', self.main)
        if self.legacy_owned:
            self.assertEqual(self.main.count('_prog('), 1)
        else:
            self.assertEqual(self.main.count('_prog('), 0)
            self.assertIn('"_prog": _prog', self.main)
            self.assertIn('prog = deps["_prog"]', self.migration_router)
            self.assertEqual(self.migration_router.count('prog(user_id,'), 1)
        self.assertGreaterEqual(self.contact_router.count('set_import_progress('), 2)
        self.assertGreaterEqual(self.migration_router.count('migration_key('), 2)
        self.assertNotIn('migration_key as _mig_llave', self.main)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/easybroker_migration.py", "exec")
        compile(self.contact_router, "routers/easybroker_contact_import.py", "exec")
        compile(self.migration_router, "routers/easybroker_migration.py", "exec")


if __name__ == "__main__":
    unittest.main()
