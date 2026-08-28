"""Permanent guard for image-runtime ownership after main.py cleanup."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainImageRuntimeCleanupTests(unittest.TestCase):
    def test_dead_image_runtime_imports_stay_out_of_main(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        qa_selfcheck = (ROOT / "routers" / "facebook_qa_selfcheck.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("import concurrent.futures", main)
        self.assertNotIn("import cv2", main)
        self.assertNotIn("import numpy as np", main)
        self.assertNotIn("CV2_AVAILABLE", main)
        self.assertNotIn("ImageEnhance", main)

        route_in_main = '@app.post("/facebook/qa-selfcheck")' in main
        if route_in_main:
            self.assertIn("from PIL import Image", main)
            self.assertIn("PIL_AVAILABLE = True", main)
            self.assertIn('if not PIL_AVAILABLE:', main)
            self.assertIn('Image.new("RGB", tam, color)', main)
        else:
            self.assertNotIn("from PIL import Image", main)
            self.assertNotIn("PIL_AVAILABLE", main)
            self.assertNotIn('Image.new("RGB", tam, color)', main)

        self.assertIn("from PIL import Image", qa_selfcheck)
        self.assertIn("PIL_AVAILABLE = True", qa_selfcheck)
        self.assertIn('if not PIL_AVAILABLE:', qa_selfcheck)
        self.assertIn('Image.new("RGB", tam, color)', qa_selfcheck)
        compile(main, "main.py", "exec")
        compile(qa_selfcheck, "routers/facebook_qa_selfcheck.py", "exec")


if __name__ == "__main__":
    unittest.main()
