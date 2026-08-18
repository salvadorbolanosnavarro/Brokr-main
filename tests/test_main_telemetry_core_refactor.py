"""Permanent guards for shared telemetry extracted from main.py."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "telemetry.py"
ROUTER = ROOT / "routers" / "telemetry.py"
MAIN = ROOT / "main.py"


class MainTelemetryCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core_source = CORE.read_text(encoding="utf-8")
        cls.router_source = ROUTER.read_text(encoding="utf-8")
        cls.main_source = MAIN.read_text(encoding="utf-8")

    def test_usage_write_lives_in_core_and_preserves_fail_soft_contract(self):
        source = self.core_source
        self.assertIn('async def track_usage(', source)
        self.assertIn(
            'await post_rows("usage_logs", payload, prefer="return=minimal", timeout=6)',
            source,
        )
        self.assertIn('except Exception:\n        pass', source)
        self.assertIn('asyncio.create_task(', source)
        self.assertIn('cache_read_input_tokens', source)
        self.assertIn('cache_creation_input_tokens', source)
        self.assertIn('GEMINI_IMAGE_USD_PER_UNIT = 0.039', source)

    def test_module_session_heartbeat_lives_in_router_and_remains_fail_soft(self):
        source = self.router_source
        self.assertIn('@router.post("/telemetria/sesion-modulo")', source)
        self.assertIn('user_id = await get_user_id_from_token(request)', source)
        self.assertIn('if modulo not in MODULOS_VALIDOS:', source)
        self.assertIn('return {"ok": False, "razon": "modulo_invalido"}', source)
        self.assertIn('if segs <= 0 or segs > 3600:', source)
        self.assertIn('return {"ok": False, "razon": "segundos_invalidos"}', source)
        self.assertIn('await post_rows(', source)
        self.assertIn('"module_sessions",', source)
        self.assertIn('prefer="return=minimal"', source)
        self.assertIn('timeout=5', source)
        self.assertIn('except Exception:\n        pass', source)
        self.assertIn('return {"ok": True}', source)

    def test_main_only_imports_shared_helpers_and_mounts_router(self):
        source = self.main_source
        self.assertIn('from core.telemetry import (', source)
        self.assertIn('from routers.telemetry import router as telemetry_router', source)
        self.assertEqual(source.count('app.include_router(telemetry_router)'), 1)
        self.assertNotIn('async def track_usage(', source)
        self.assertNotIn('def _track_anthropic(', source)
        self.assertNotIn('@app.post("/telemetria/sesion-modulo")', source)
        self.assertNotIn('/rest/v1/usage_logs', source)
        self.assertNotIn('/rest/v1/module_sessions', source)
        compile(self.core_source, "core/telemetry.py", "exec")
        compile(self.router_source, "routers/telemetry.py", "exec")
        compile(source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
