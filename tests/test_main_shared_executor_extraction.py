"""Permanent guard for the shared bounded thread pool extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainSharedExecutorExtractionTests(unittest.TestCase):
    def test_shared_pool_lives_once_in_core_and_consumers_delegate(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        core = (ROOT / "core" / "executors.py").read_text(encoding="utf-8")
        image_cleaner = (ROOT / "routers" / "image_cleaner.py").read_text(encoding="utf-8")
        machotes = (ROOT / "routers" / "machotes.py").read_text(encoding="utf-8")

        self.assertNotIn("from core.executors import _thread_pool", main)
        self.assertNotIn("_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)", main)
        self.assertIn("_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)", core)
        self.assertIn("from core.executors import _thread_pool", image_cleaner)
        self.assertIn("from core.executors import _thread_pool", machotes)
        self.assertNotIn("ThreadPoolExecutor(", image_cleaner)
        self.assertNotIn("ThreadPoolExecutor(", machotes)
        compile(core, "core/executors.py", "exec")
        compile(main, "main.py", "exec")
        compile(image_cleaner, "routers/image_cleaner.py", "exec")
        compile(machotes, "routers/machotes.py", "exec")


if __name__ == "__main__":
    unittest.main()
