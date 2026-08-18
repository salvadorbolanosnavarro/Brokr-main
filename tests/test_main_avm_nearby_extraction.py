"""Permanent guard for AVM nearby extraction from main.py."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainAvmNearbyExtractionTests(unittest.TestCase):
    def test_main_mounts_router_and_no_longer_owns_nearby_route(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "avm_nearby.py").read_text(encoding="utf-8")

        self.assertIn("from routers.avm_nearby import router as avm_nearby_router", main)
        self.assertIn("app.include_router(avm_nearby_router)", main)
        self.assertNotIn('@app.post("/api/comparables-cercanos")', main)
        self.assertNotIn("async def comparables_cercanos(", main)
        self.assertNotIn("class CercanosRequest(", main)

        self.assertIn('@router.post("/api/comparables-cercanos")', router)
        self.assertIn('await call_public_rpc(', router)
        self.assertIn('"buscar_cercanos"', router)
        self.assertIn('accepted_statuses=(200, 201)', router)
        self.assertIn('except httpx.HTTPStatusError:', router)
        self.assertIn('await get_public_rows(', router)
        self.assertIn('"propiedades_avm"', router)
        self.assertIn('"ciudad": "eq.Morelia"', router)
        self.assertIn('cache_set(cache_key, resultado, ttl=3600)', router)
        self.assertIn('detail="SUPABASE_URL o SUPABASE_ANON_KEY no configuradas"', router)
        compile(router, "routers/avm_nearby.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
