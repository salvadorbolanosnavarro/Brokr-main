from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "easybroker_migration.py"
CONTACT_ROUTER = ROOT / "routers" / "easybroker_contact_import.py"


class EasyBrokerMigrationStateExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")
        cls.contact_router = CONTACT_ROUTER.read_text(encoding="utf-8")

    def test_shared_state_lives_in_core(self):
        self.assertIn('MIGRACIONES: dict = {}', self.core)
        self.assertIn('PROGRESO_IMPORT: dict = {}', self.core)
        self.assertNotIn('_MIGRACIONES: dict = {}', self.main)
        self.assertNotIn('_PROGRESO_IMPORT: dict = {}', self.main)
        self.assertIn('MIGRACIONES as _MIGRACIONES', self.main)
        self.assertIn('PROGRESO_IMPORT as _PROGRESO_IMPORT', self.main)

    def test_progress_and_key_contracts_are_preserved(self):
        c = self.core
        self.assertIn('def set_import_progress(user_id: str, texto: str)', c)
        self.assertIn('PROGRESO_IMPORT[user_id] = texto', c)
        self.assertIn('except Exception:\n        pass', c)
        self.assertIn('def migration_key(org_id, user_id):', c)
        self.assertIn('return f"org:{org_id}" if org_id else f"user:{user_id}"', c)
        self.assertIn('set_import_progress as _prog', self.main)
        self.assertIn('migration_key as _mig_llave', self.main)
        self.assertEqual(self.main.count('_prog('), 1)
        self.assertGreaterEqual(self.contact_router.count('set_import_progress('), 2)
        self.assertGreaterEqual(self.main.count('_mig_llave('), 2)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/easybroker_migration.py", "exec")
        compile(self.contact_router, "routers/easybroker_contact_import.py", "exec")


if __name__ == "__main__":
    unittest.main()
