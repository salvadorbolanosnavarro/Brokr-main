"""Permanent guard for personalized contract-template extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainMachotesExtractionTests(unittest.TestCase):
    def test_main_mounts_router_and_no_longer_owns_machotes(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "machotes.py").read_text(encoding="utf-8")

        self.assertIn("from routers.machotes import router as machotes_router", main)
        self.assertIn("app.include_router(machotes_router)", main)
        for legacy in (
            '@app.post("/contrato/machote/abrir")',
            '@app.post("/contrato/machote/sugerir")',
            '@app.post("/contrato/machote/crear")',
            '@app.get("/contrato/machotes")',
            '@app.delete("/contrato/machote/{machote_id}")',
            "async def _machote_o_404(",
        ):
            self.assertNotIn(legacy, main)

        self.assertIn('@router.post("/contrato/machote/abrir")', router)
        self.assertIn('@router.post("/contrato/machote/sugerir")', router)
        self.assertIn('@router.post("/contrato/machote/crear")', router)
        self.assertIn('@router.get("/contrato/machotes")', router)
        self.assertIn('@router.get("/contrato/machote/{machote_id}")', router)
        self.assertIn('@router.patch("/contrato/machote/{machote_id}")', router)
        self.assertIn('@router.post("/contrato/machote/{machote_id}/preview")', router)
        self.assertIn('@router.post("/contrato/machote/{machote_id}/generar")', router)
        self.assertIn('@router.delete("/contrato/machote/{machote_id}")', router)

    def test_storage_database_and_executor_contracts_remain_explicit(self):
        router = (ROOT / "routers" / "machotes.py").read_text(encoding="utf-8")
        self.assertIn('MACHOTES_BUCKET = "machotes-contrato"', router)
        self.assertIn('MACHOTE_MAX_BYTES = 12 * 1024 * 1024', router)
        self.assertIn('from core.executors import _thread_pool', router)
        self.assertIn('await post_rows(', router)
        self.assertIn('accepted_statuses=(200, 201)', router)
        self.assertIn('await patch_rows(', router)
        self.assertIn('accepted_statuses=(200, 204)', router)
        self.assertIn('await delete_rows(', router)
        self.assertIn('prefer="return=minimal"', router)
        self.assertIn('f"{settings.supabase_url}/storage/v1/object/{MACHOTES_BUCKET}/{path}"', router)
        self.assertIn('_track_anthropic(', router)
        self.assertIn('api_key=settings.anthropic_api_key', router)
        compile(router, "routers/machotes.py", "exec")


if __name__ == "__main__":
    unittest.main()
