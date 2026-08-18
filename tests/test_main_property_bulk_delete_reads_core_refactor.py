"""Permanent guards for property bulk-delete Core reads and delete routing."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainPropertyBulkDeleteReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/propiedades/eliminar-masivo")')
        end = cls.source.index('\n\n@app.post("/contactos/eliminar-masivo")', start)
        cls.block = cls.source[start:end]

    def test_direct_verification_gets_stay_removed(self):
        self.assertNotIn('client.get(f"{SUPABASE_URL}/rest/v1/propiedades"', self.block)

    def test_core_reads_and_delete_preserve_storage_cleanup(self):
        block = self.block
        self.assertIn('filas = await get_rows(', block)
        self.assertIn('filas.extend(await get_rows(', block)
        self.assertIn('"propiedades",', block)
        self.assertIn('"select": "id,fotos"', block)
        self.assertIn('timeout=60', block)
        self.assertIn('raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")', block)

        self.assertIn('await delete_rows(', block)
        self.assertIn('{**filtro, "id": f"in.({lista})"}', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertNotIn('/rest/v1/propiedades', block)

        self.assertIn('asyncio.create_task(_borrar_fotos_storage(nombres))', block)
        self.assertLess(block.index('await delete_rows('), block.index('asyncio.create_task(_borrar_fotos_storage(nombres))'))


if __name__ == "__main__":
    unittest.main()
