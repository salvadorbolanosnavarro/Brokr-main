"""Permanent guard for dead image-runtime imports removed from main.py."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainImageRuntimeCleanupTests(unittest.TestCase):
    def test_dead_image_runtime_imports_stay_out_of_main(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("import concurrent.futures", main)
        self.assertNotIn("import cv2", main)
        self.assertNotIn("import numpy as np", main)
        self.assertNotIn("CV2_AVAILABLE", main)
        self.assertNotIn("ImageEnhance", main)
        self.assertIn("from PIL import Image", main)
        self.assertIn("PIL_AVAILABLE = True", main)
        self.assertIn('if not PIL_AVAILABLE:', main)
        self.assertIn('Image.new("RGB", tam, color)', main)
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
