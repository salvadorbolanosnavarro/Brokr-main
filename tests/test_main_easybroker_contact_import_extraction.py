from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_contact_import.py"
FILE_ROUTER = ROOT / "routers" / "contact_file_import.py"


class EasyBrokerContactImportExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.file_router = FILE_ROUTER.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertIn('@router.post("/contactos/importar-eb")', self.router)
        self.assertNotIn('@app.post("/contactos/importar-eb")', self.main)
        self.assertIn('app.include_router(easybroker_contact_import_router)', self.main)
        if '@app.post("/contactos/importar-archivo")' in self.main:
            self.assertNotIn('create_contact_file_import_router', self.main)
        else:
            self.assertNotIn('@app.post("/contactos/importar-archivo")', self.main)
            self.assertIn('@router.post("/contactos/importar-archivo")', self.file_router)
            self.assertIn('app.include_router(create_contact_file_import_router(lambda: {', self.main)

    def test_easybroker_paging_backoff_and_circuit_breaker_are_preserved(self):
        r = self.router
        self.assertIn('f"{EB_BASE}/contacts"', r)
        self.assertIn('{"page": page, "limit": 50}', r)
        self.assertIn('f"{EB_BASE}/contacts/{cid}"', r)
        self.assertIn('for i in range(0, len(eb_ids), _EB_LOTE):', r)
        self.assertIn('_EB_PAUSA_LOTE - (time.monotonic() - inicio_lote)', r)
        self.assertIn('if lotes_fallidos_seguidos >= 4:', r)
        self.assertIn('status_code=429', r)
        self.assertIn('set_import_progress(user_id, f"contactos', r)

    def test_org_wide_dedupe_and_fill_only_empty_contract_are_preserved(self):
        r = self.router
        self.assertIn('org_id_import = await get_org_id_for_user(user_id)', r)
        self.assertIn('mapa_ag = await map_org_agents(org_id_import, user_id)', r)
        self.assertIn('existing_by_tel', r)
        self.assertIn('existing_by_email', r)
        self.assertIn('if not existente.get(campo) and m.get(campo):', r)
        self.assertIn('union = list(dict.fromkeys([*prev, *m["etiquetas"]]))', r)
        self.assertIn('accepted_statuses=(200, 204)', r)
        self.assertIn('accepted_statuses=(200, 201)', r)
        self.assertNotIn('/rest/v1/', r)

    def test_legacy_http_failure_semantics_are_preserved(self):
        r = self.router
        self.assertIn('except httpx.HTTPStatusError:\n        existing = []', r)
        self.assertGreaterEqual(r.count('except httpx.HTTPStatusError:'), 3)
        self.assertIn('except Exception:\n            pass', r)
        self.assertIn('EasyBroker no respondió tras varios intentos', r)
        self.assertIn('Tu plan de EasyBroker no tiene acceso a contactos vía API', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/easybroker_contact_import.py", "exec")
        compile(self.file_router, "routers/contact_file_import.py", "exec")


if __name__ == "__main__":
    unittest.main()
