"""Permanent guard for ficha-manual AI description extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainFichaManualExtractionTests(unittest.TestCase):
    def test_manual_description_preserves_ai_contract(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "ficha_manual.py").read_text(encoding="utf-8")

        self.assertIn('@router.post("/ficha-manual/descripcion")', router)
        self.assertIn('exigir_cupo(request, _uid)', router)
        self.assertIn('exigir_sesion(request, _uid)', router)
        self.assertIn('detail="ANTHROPIC_API_KEY no configurada"', router)
        self.assertIn('httpx.AsyncClient(timeout=30)', router)
        self.assertIn('"model": "claude-sonnet-4-6"', router)
        self.assertIn('"max_tokens": 350', router)
        self.assertIn('_track_anthropic(', router)
        self.assertIn('"ficha-manual"', router)
        self.assertIn('"/ficha-manual/descripcion"', router)
        self.assertIn('return {"descripcion": descripcion}', router)
        self.assertIn('from routers.ficha_manual import router as ficha_manual_router', main)
        self.assertNotIn('@app.post("/ficha-manual/descripcion")', main)
        compile(router, "routers/ficha_manual.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
