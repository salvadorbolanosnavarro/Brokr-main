"""Keep _revisar_recordatorios's tareas read and reminder patch behind core.database."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "reminders.py"
MAIN = ROOT / "main.py"


class MainReminderTasksReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROUTER.read_text(encoding="utf-8")
        start = source.index("async def _revisar_recordatorios():")
        end = source.index("\n\nasync def _recordatorios_loop():", start)
        cls.block = source[start:end]
        cls.main_source = MAIN.read_text(encoding="utf-8")

    def test_read_uses_core_and_preserves_logs(self):
        block = self.block
        self.assertIn('tareas = await get_rows(\n                "tareas",', block)
        self.assertIn('"select": "id,user_id,titulo,fecha_entrega,recordatorio_minutos_antes"', block)
        self.assertIn('"completada": "eq.false", "recordatorio_enviado": "eq.false"', block)
        self.assertIn('"fecha_entrega": "not.is.null", "limit": "200"', block)
        self.assertIn("timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError as e:", block)
        self.assertIn('texto = e.response.text if e.response is not None else ""', block)
        self.assertIn('_recordatorios_log.warning("No se pudo leer tareas para recordatorios: %s", texto[:200])', block)
        self.assertIn('_recordatorios_log.error("Error consultando tareas para recordatorios: %s", e)', block)

    def test_downstream_push_and_patch_remain_intact(self):
        block = self.block
        self.assertIn('await enviar_push(', block)
        self.assertIn('await patch_rows(', block)
        self.assertIn('"tareas"', block)
        self.assertIn('{"id": f"eq.{t[\'id\']}"}', block)
        self.assertIn('{"recordatorio_enviado": True}', block)
        self.assertEqual(block.count("/rest/v1/tareas"), 0)
        read_end = block.index("    for t in tareas:")
        self.assertNotIn("/rest/v1/tareas", block[:read_end])
        self.assertNotIn("Authorization", block[:read_end])
        self.assertIn('from routers.reminders import router as reminders_router', self.main_source)
        self.assertNotIn('async def _revisar_recordatorios()', self.main_source)


if __name__ == "__main__":
    unittest.main()
