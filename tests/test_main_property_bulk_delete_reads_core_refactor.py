"""Permanent guards for property bulk-delete verification Core reads."""
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

    def test_core_reads_preserve_delete_and_storage_cleanup(self):
        block = self.block
        self.assertIn('filas = await get_rows(', block)
        self.assertIn('filas.extend(await get_rows(', block)
        self.assertIn('"propiedades",', block)
        self.assertIn('"select": "id,fotos"', block)
        self.assertIn('timeout=60', block)
        self.assertIn('raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")', block)
        self.assertIn('rd = await client.delete(\n                    f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        self.assertIn('asyncio.create_task(_borrar_fotos_storage(nombres))', block)


if __name__ == "__main__":
    unittest.main()
