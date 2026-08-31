"""Permanent guard for comparables PostGIS RPC routed through core.database."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "avm_nearby.py"


class MainComparablesPublicRpcCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")
        cls.main_source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@router.post("/api/comparables-cercanos")')
        cls.block = cls.source[start:]

    def test_rpc_routes_through_public_core_with_exact_statuses(self):
        block = self.block
        self.assertIn('await call_public_rpc(', block)
        self.assertIn('"buscar_cercanos"', block)
        self.assertIn('payload,', block)
        self.assertIn('timeout=15', block)
        self.assertIn('accepted_statuses=(200, 201)', block)
        self.assertNotIn('/rest/v1/rpc/buscar_cercanos', block)
        self.assertNotIn('headers = {', block)

    def test_http_fallback_and_transport_contract_are_preserved(self):
        block = self.block
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('items = await get_public_rows(', block)
        self.assertIn('"propiedades_avm"', block)
        rpc_tail = block[block.index('try:\n        items = await call_public_rpc('):]
        self.assertNotIn('except Exception:', rpc_tail.split('comparables = []', 1)[0])

    def test_main_mounts_router_instead_of_owning_rpc_primitive(self):
        self.assertIn('from core.database import call_public_rpc, get_public_rows', self.source)
        self.assertIn('from routers.avm_nearby import router as avm_nearby_router', self.main_source)
        self.assertNotIn('@app.post("/api/comparables-cercanos")', self.main_source)


if __name__ == '__main__':
    unittest.main()
