from pathlib import Path
import unittest

from scripts.refactor_main_rental_docx_safety_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class RentalDOCXSafetyTransformTests(unittest.TestCase):
    def test_primary_and_supplemental_docx_are_validated_before_python_docx(self):
        transformed = transform_source(MAIN.read_text(encoding="utf-8"))
        self.assertIn("from core.documents import validate_docx_archive", transformed)
        self.assertIn("validate_docx_archive(content)\n            from docx import Document as DocxDocument", transformed)
        self.assertIn("validate_docx_archive(raw)\n                from docx import Document as _DocxDocument", transformed)

    def test_existing_primary_error_contract_is_kept(self):
        transformed = transform_source(MAIN.read_text(encoding="utf-8"))
        self.assertIn('raise HTTPException(status_code=400, detail=f"No se pudo leer el DOCX: {e}")', transformed)
        self.assertIn("except HTTPException:\n            raise", transformed)

    def test_supplemental_invalid_document_remains_fail_soft(self):
        transformed = transform_source(MAIN.read_text(encoding="utf-8"))
        marker = 'elif "wordprocessingml" in ct or n.endswith(".docx"):'
        block = transformed.split(marker, 1)[1].split('elif ct.startswith("image/")', 1)[0]
        self.assertIn("validate_docx_archive(raw)", block)
        self.assertIn("except Exception:\n                pass", block)

    def test_transform_is_idempotent_and_compiles(self):
        source = MAIN.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))
        compile(once, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
