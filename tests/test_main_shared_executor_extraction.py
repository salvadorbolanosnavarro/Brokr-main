"""Permanent guard for the shared bounded thread pool extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainSharedExecutorExtractionTests(unittest.TestCase):
    def test_main_delegates_shared_pool_to_core(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        core = (ROOT / "core" / "executors.py").read_text(encoding="utf-8")

        self.assertIn("from core.executors import _thread_pool", main)
        self.assertNotIn("_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)", main)
        self.assertIn("_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)", core)
        compile(core, "core/executors.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
