"""Permanent guard for shared process-local PDF store extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainPdfStoreExtractionTests(unittest.TestCase):
    def test_main_uses_shared_core_store(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        core = (ROOT / "core" / "pdf_store.py").read_text(encoding="utf-8")
        self.assertIn("from core.pdf_store import _pdf_store", main)
        self.assertNotIn("_pdf_store: dict = {}", main)
        self.assertIn("_pdf_store: dict[str, tuple[bytes, str]] = {}", core)
        compile(core, "core/pdf_store.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
