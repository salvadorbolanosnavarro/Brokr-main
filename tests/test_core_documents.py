import io
from pathlib import Path
import unittest
import zipfile

from core.documents import UnsafeDocument, validate_docx_archive


class DOCXArchiveSafetyTests(unittest.TestCase):
    def make_docx(self, entries: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in entries.items():
                zf.writestr(name, data)
        return buf.getvalue()

    def valid_minimal_docx(self, extra: dict[str, bytes] | None = None) -> bytes:
        entries = {
            "[Content_Types].xml": b"<Types/>",
            "word/document.xml": b"<w:document xmlns:w='x'/>",
        }
        entries.update(extra or {})
        return self.make_docx(entries)

    def test_accepts_bounded_docx_container(self):
        validate_docx_archive(self.valid_minimal_docx())

    def test_rejects_non_zip_and_non_docx_zip(self):
        with self.assertRaises(UnsafeDocument):
            validate_docx_archive(b"not-a-zip")
        with self.assertRaises(UnsafeDocument):
            validate_docx_archive(self.make_docx({"x.txt": b"x"}))

    def test_rejects_declared_uncompressed_size_above_limit(self):
        content = self.valid_minimal_docx({"word/huge.xml": b"A" * 4096})
        with self.assertRaises(UnsafeDocument):
            validate_docx_archive(content, max_uncompressed_bytes=1024)

    def test_rejects_single_huge_entry(self):
        content = self.valid_minimal_docx({"word/huge.xml": b"A" * 4096})
        with self.assertRaises(UnsafeDocument):
            validate_docx_archive(content, max_single_entry_bytes=1024)

    def test_rejects_excessive_entry_count(self):
        content = self.valid_minimal_docx({f"word/x{i}.xml": b"x" for i in range(10)})
        with self.assertRaises(UnsafeDocument):
            validate_docx_archive(content, max_entries=5)


if __name__ == "__main__":
    unittest.main()
