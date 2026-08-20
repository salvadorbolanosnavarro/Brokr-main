from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_migration.py"


class EasyBrokerMigrationRouterExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_routes_live_only_in_router(self):
        self.assertIn('@router.post("/easybroker/migracion/iniciar")', self.router)
        self.assertIn('@router.get("/easybroker/migracion/estado")', self.router)
        self.assertNotIn('@app.post("/easybroker/migracion/iniciar")', self.main)
        self.assertNotIn('@app.get("/easybroker/migracion/estado")', self.main)
        self.assertIn('app.include_router(easybroker_migration_router)', self.main)
        self.assertIn('@app.post("/easybroker/import-stats")', self.main)

    def test_coordinator_contract_is_preserved(self):
        r = self.router
        self.assertIn('base = f"http://127.0.0.1:{legacy_main_settings.port}"', r)
        self.assertIn('(\"propiedades\", \"/easybroker/import-all\", {\"fotos_diferidas\": True})', r)
        self.assertIn('(\"contactos\", \"/contactos/importar-eb\", None)', r)
        self.assertIn('(\"historial\", \"/easybroker/import-stats\", None)', r)
        self.assertIn('httpx.AsyncClient(timeout=1800)', r)
        self.assertIn('time.time() - previa.get("inicio", 0) < 1800', r)
        self.assertIn('asyncio.create_task(_job_migracion_eb(llave, auth_header))', r)

    def test_shared_state_and_auth_contract_are_preserved(self):
        r = self.router
        self.assertIn('from core.easybroker_migration import MIGRACIONES, PROGRESO_IMPORT, migration_key', r)
        self.assertIn('await get_user_id_from_token(request)', r)
        self.assertIn('await get_org_id_for_user(user_id)', r)
        self.assertIn('detalle": PROGRESO_IMPORT.get(user_id)', r)
        self.assertIn('Tu sesión expiró. Vuelve a iniciar sesión.', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/easybroker_migration.py", "exec")


if __name__ == "__main__":
    unittest.main()
