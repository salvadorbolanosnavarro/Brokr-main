"""Permanent guard for standard DOCX contract extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainContractsBasicExtractionTests(unittest.TestCase):
    def test_main_mounts_router_and_no_longer_owns_standard_contract(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "contracts_basic.py").read_text(encoding="utf-8")

        self.assertIn("from routers.contracts_basic import router as contracts_basic_router", main)
        self.assertIn("app.include_router(contracts_basic_router)", main)
        self.assertNotIn('@app.post("/contrato")', main)
        self.assertNotIn("class ContratoRequest(", main)
        self.assertNotIn("async def generar_contrato(", main)

        self.assertIn('@router.post("/contrato")', router)
        self.assertIn('"model": "llama-3.3-70b-versatile"', router)
        self.assertIn('"max_tokens": 2000', router)
        self.assertIn('"temperature": 0.3', router)
        self.assertIn('_track_groq(', router)
        self.assertIn('clausulas_redactadas = req.clausulas_especiales', router)
        self.assertIn('_ROOT / "generar_contrato.py"', router)
        self.assertIn('timeout=30', router)
        self.assertIn('"arrendamiento": "Contrato_Arrendamiento.docx"', router)
        self.assertIn('"promesa": "Promesa_Compraventa.docx"', router)
        self.assertIn('os.unlink(json_path)', router)
        compile(router, "routers/contracts_basic.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
