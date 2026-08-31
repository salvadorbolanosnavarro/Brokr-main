"""Dependency-manifest regression guards established during architecture cleanup."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "requirements.txt"


class DependencyManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = {
            line.strip().lower()
            for line in REQ.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

    def test_removed_unused_heavy_dependencies_stay_removed(self):
        self.assertNotIn("openpyxl", self.lines)
        self.assertNotIn("opencv-python-headless", self.lines)

    def test_known_runtime_dependencies_remain_declared(self):
        for package in (
            "httpx[http2]",
            "beautifulsoup4",
            "python-docx",
            "playwright",
            "pillow",
            "python-multipart",
            "pyjwt",
            "cryptography",
            "pypdf",
        ):
            self.assertIn(package, self.lines)


if __name__ == "__main__":
    unittest.main()
