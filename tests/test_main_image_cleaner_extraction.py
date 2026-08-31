"""Permanent guard for image-cleaner extraction from main.py."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainImageCleanerExtractionTests(unittest.TestCase):
    def test_main_mounts_router_and_no_longer_owns_image_pipeline(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "image_cleaner.py").read_text(encoding="utf-8")

        self.assertIn("from routers.image_cleaner import router as image_cleaner_router", main)
        self.assertIn("app.include_router(image_cleaner_router)", main)
        self.assertNotIn('@app.post("/images/clean")', main)
        self.assertNotIn("def _process_image_sync(", main)
        self.assertNotIn("async def _process_with_gemini(", main)

        self.assertIn('@router.post("/images/clean")', router)
        self.assertIn("from core.executors import _thread_pool", router)
        self.assertIn("await loop.run_in_executor(_thread_pool, _process_image_sync, raw, ct)", router)
        self.assertIn("exigir_cupo(request, user_id)", router)
        self.assertIn("exigir_sesion(request, user_id)", router)
        self.assertIn("settings.gemini_image_model", router)
        self.assertIn("_track_gemini_image(", router)
        self.assertIn("r.status_code == 429", router)
        self.assertIn("return {\"images\": list(results)}", router)
        compile(router, "routers/image_cleaner.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
