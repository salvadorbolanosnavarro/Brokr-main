from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_import_stats.py"


class EasyBrokerImportStatsExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertIn('@router.post("/easybroker/import-stats")', self.router)
        self.assertNotIn('@app.post("/easybroker/import-stats")', self.main)
        self.assertIn('app.include_router(easybroker_import_stats_router)', self.main)

    def test_read_and_paging_contracts_are_preserved(self):
        r = self.router
        self.assertIn('"propiedades"', r)
        self.assertIn('"contactos"', r)
        self.assertIn('"contactos_propiedades"', r)
        self.assertIn('f"{EB_BASE}/contact_requests"', r)
        self.assertIn('while pagina <= 400:', r)
        self.assertIn('[("limit", 50), ("page", pagina)]', r)
        self.assertIn('timeout=30.0', r)
        self.assertIn('Tu API key de EasyBroker fue rechazada.', r)
        self.assertIn('no tiene acceso a solicitudes de contacto vía API', r)

    def test_grouping_and_batch_write_contracts_are_preserved(self):
        r = self.router
        self.assertIn('llave = tel or email or f"nombre:{nombre.lower()}"', r)
        self.assertIn('fecha_real = min(g["fechas"]) if g["fechas"] else ahora', r)
        self.assertIn('"es_potencial": True', r)
        self.assertIn('for i in range(0, len(nuevos_lote), 100):', r)
        self.assertIn('for i in range(0, len(ids_marcar), 200):', r)
        self.assertIn('for i in range(0, len(vinculos_validos), 200):', r)
        self.assertIn('accepted_statuses=(200, 201, 204)', r)
        self.assertIn('accepted_statuses=(200, 204)', r)
        self.assertNotIn('/rest/v1/', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/easybroker_import_stats.py", "exec")


if __name__ == "__main__":
    unittest.main()
