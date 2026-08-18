"""Permanent guard for task-reminder extraction from main.py."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainRemindersExtractionTests(unittest.TestCase):
    def test_main_mounts_reminders_router_and_no_longer_owns_loop(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "reminders.py").read_text(encoding="utf-8")

        self.assertIn("from routers.reminders import router as reminders_router", main)
        self.assertIn("app.include_router(reminders_router)", main)
        self.assertNotIn("async def _revisar_recordatorios()", main)
        self.assertNotIn("async def _recordatorios_loop()", main)
        self.assertNotIn("async def _iniciar_recordatorios()", main)

        self.assertIn('@router.on_event("startup")', router)
        self.assertIn("asyncio.create_task(_recordatorios_loop())", router)
        self.assertIn("await asyncio.sleep(300)", router)
        self.assertIn('"completada": "eq.false"', router)
        self.assertIn('"recordatorio_enviado": "eq.false"', router)
        self.assertIn('"limit": "200"', router)
        self.assertIn('await patch_rows(', router)
        self.assertIn('{"recordatorio_enviado": True}', router)
        self.assertIn('except httpx.HTTPStatusError as e:', router)
        compile(router, "routers/reminders.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
