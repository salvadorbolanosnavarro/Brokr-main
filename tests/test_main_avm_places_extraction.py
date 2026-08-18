"""Permanent guards for Google Places AVM colonia extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainAvmPlacesExtractionTests(unittest.TestCase):
    def test_places_colonia_contract_is_preserved(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "avm_places.py").read_text(encoding="utf-8")

        self.assertIn('@router.get("/api/colonias")', router)
        self.assertIn('if len(texto) < 3:', router)
        self.assertIn('return {"colonias": [], "error": "GOOGLE_PLACES_KEY no configurada"}', router)
        self.assertIn('httpx.AsyncClient(timeout=15)', router)
        self.assertIn('"locationbias": "circle:50000@19.7059504,-101.1949825"', router)
        self.assertIn('["sublocality", "sublocality_level_1", "neighborhood"]', router)
        self.assertIn('httpx.AsyncClient(timeout=10)', router)
        self.assertIn('resultado = {"colonias": colonias[:6]}', router)
        self.assertIn('cache_set(cache_key, resultado, ttl=86400)', router)
        self.assertIn('from routers.avm_places import router as avm_places_router', main)
        self.assertNotIn('@app.get("/api/colonias")', main)
        compile(router, "routers/avm_places.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
