"""Permanent guards for Apify/Inmuebles24 AVM extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainAvmApifyExtractionTests(unittest.TestCase):
    def test_apify_avm_contract_is_preserved_in_router(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "avm_apify.py").read_text(encoding="utf-8")

        self.assertIn('APIFY_ACTOR = "azzouzana~inmuebles24-scraper-pro-by-search-url"', router)
        self.assertIn('@router.post("/api/comparables")', router)
        self.assertIn('detail="APIFY_API_KEY no configurada en el servidor"', router)
        self.assertIn('httpx.AsyncClient(timeout=90)', router)
        self.assertIn('except httpx.TimeoutException:', router)
        self.assertIn('status_code=504, detail="Apify tardó demasiado. Intenta de nuevo."', router)
        self.assertIn('if r.status_code not in (200, 201):', router)
        self.assertIn('detail=f"Error de Apify: {r.status_code} — {r.text[:300]}"', router)
        self.assertIn('if not isinstance(items, list):', router)
        self.assertIn('cache_set(cache_key, resultado, ttl=7200)', router)
        self.assertIn('def normalizar_listing(item: dict) -> dict:', router)
        self.assertIn('if moneda == "USD":\n        return None', router)
        self.assertIn('from routers.avm_apify import router as avm_apify_router', main)
        self.assertNotIn('@app.post("/api/comparables")', main)
        self.assertNotIn('def normalizar_listing(', main)
        compile(router, "routers/avm_apify.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
