from pathlib import Path
import unittest

from scripts.refactor_machotes_docx_safety_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "routers" / "machotes.py"


class MachotesDOCXSafetyTransformTests(unittest.TestCase):
    def test_transform_validates_archive_before_downstream_parser(self):
        source = SOURCE.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from core.documents import UnsafeDocument, validate_docx_archive", transformed)
        self.assertIn("validate_docx_archive(content)", transformed)
        self.assertIn("se expande más de lo permitido", transformed)
        self.assertLess(
            transformed.index("validate_docx_archive(content)"),
            transformed.index('@router.post("/contrato/machote/abrir")'),
        )

    def test_existing_upload_limits_and_docx_extension_guard_remain(self):
        transformed = transform_source(SOURCE.read_text(encoding="utf-8"))
        self.assertIn("if len(content) > MACHOTE_MAX_BYTES:", transformed)
        self.assertIn('endswith(".docx")', transformed)
        self.assertIn("MACHOTE_MAX_BYTES = 12 * 1024 * 1024", transformed)

    def test_transform_is_idempotent_and_compiles(self):
        source = SOURCE.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))
        compile(once, "routers/machotes.py", "exec")


if __name__ == "__main__":
    unittest.main()
