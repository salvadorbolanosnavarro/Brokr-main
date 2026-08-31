"""Permanent guards for shared PDF download router extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainPdfDownloadsExtractionTests(unittest.TestCase):
    def test_download_routes_share_core_store_and_preserve_headers(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "pdf_downloads.py").read_text(encoding="utf-8")

        self.assertIn("from core.pdf_store import _pdf_store", router)
        self.assertIn('@router.get("/avm-pdf/{token}")', router)
        self.assertIn('@router.get("/isr-pdf/{token}")', router)
        self.assertIn('@router.get("/ficha-pdf/{token}")', router)
        self.assertIn('detail="PDF no encontrado o expirado"', router)
        self.assertIn('"Access-Control-Allow-Origin": "*"', router)
        self.assertIn('"Access-Control-Allow-Methods": "GET"', router)
        self.assertIn('"Cache-Control": "no-store"', router)
        self.assertIn('media_type="application/pdf"', router)

        self.assertIn(
            'from routers.pdf_downloads import router as pdf_downloads_router',
            main,
        )
        self.assertNotIn('@app.get("/avm-pdf/{token}")', main)
        self.assertNotIn('@app.get("/isr-pdf/{token}")', main)
        self.assertNotIn('@app.get("/ficha-pdf/{token}")', main)
        compile(router, "routers/pdf_downloads.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
