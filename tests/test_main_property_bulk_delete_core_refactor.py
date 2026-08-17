"""Permanent guard for property bulk DELETE routed through core.database."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainPropertyBulkDeleteCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = MAIN.read_text(encoding="utf-8")
        start = source.index('@app.post("/propiedades/eliminar-masivo")')
        end = source.index('@app.post("/contactos/eliminar-masivo")', start)
        cls.block = source[start:end]

    def test_bulk_delete_routes_through_core_with_exact_status_contract(self):
        block = self.block
        self.assertIn('for i in range(0, len(ids_reales), 200):', block)
        self.assertIn('await delete_rows(', block)
        self.assertIn('"propiedades"', block)
        self.assertIn('{**filtro, "id": f"in.({lista})"}', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('eliminadas += len(lote)', block)
        self.assertIn('except httpx.HTTPStatusError:\n                    pass', block)
        self.assertNotIn('/rest/v1/propiedades', block)

    def test_transport_failure_still_reaches_outer_500_and_photo_cleanup_stays_after_rows(self):
        block = self.block
        self.assertIn('except Exception:\n        raise HTTPException(status_code=500, detail="No se pudieron borrar todas las propiedades.")', block)
        self.assertIn('asyncio.create_task(_borrar_fotos_storage(nombres))', block)
        self.assertLess(block.index('await delete_rows('), block.index('asyncio.create_task(_borrar_fotos_storage(nombres))'))


if __name__ == "__main__":
    unittest.main()
