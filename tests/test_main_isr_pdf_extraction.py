"""Permanent guard for ISR PDF generation extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainIsrPdfExtractionTests(unittest.TestCase):
    def test_isr_pdf_route_preserves_generation_contract(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "isr_pdf.py").read_text(encoding="utf-8")

        self.assertIn('@router.post("/isr-pdf")', router)
        self.assertIn('exigir_cupo(request, _uid)', router)
        self.assertIn('exigir_sesion(request, _uid)', router)
        self.assertIn('detail="HTML vacío"', router)
        self.assertIn('pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])', router)
        self.assertIn('wait_until="domcontentloaded"', router)
        self.assertIn('await page.wait_for_timeout(300)', router)
        self.assertIn('format="A4"', router)
        self.assertIn('"top": "20mm"', router)
        self.assertIn('filename = p.get("filename", "ISR_Brokr.pdf")', router)
        self.assertIn('_pdf_store[token] = (pdf_bytes, filename)', router)
        self.assertIn('if len(_pdf_store) > 50:', router)
        self.assertIn(
            'from routers.isr_pdf import router as isr_pdf_router',
            main,
        )
        self.assertNotIn('@app.post("/isr-pdf")', main)
        compile(router, "routers/isr_pdf.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
