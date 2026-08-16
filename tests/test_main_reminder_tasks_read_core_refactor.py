"""Dry-run guards for _revisar_recordatorios's initial tareas read migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_reminder_tasks_read_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("reminder_tasks_read_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainReminderTasksReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_only_initial_tareas_read(self):
        transformed = _load_transform()(self.source)
        start = transformed.index("async def _revisar_recordatorios():")
        end = transformed.index("\n\nasync def _recordatorios_loop():", start)
        block = transformed[start:end]
        self.assertEqual(block.count("/rest/v1/tareas"), 1)  # the later PATCH remains legacy
        compile(transformed, "main.py", "exec")

    def test_read_uses_core_and_preserves_logs_and_patch(self):
        transformed = _load_transform()(self.source)
        start = transformed.index("async def _revisar_recordatorios():")
        end = transformed.index("\n\nasync def _recordatorios_loop():", start)
        block = transformed[start:end]

        self.assertIn('tareas = await get_rows(\n                "tareas",', block)
        self.assertIn('"select": "id,user_id,titulo,fecha_entrega,recordatorio_minutos_antes"', block)
        self.assertIn('"completada": "eq.false", "recordatorio_enviado": "eq.false"', block)
        self.assertIn('"fecha_entrega": "not.is.null", "limit": "200"', block)
        self.assertIn("timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError as e:", block)
        self.assertIn('texto = e.response.text if e.response is not None else ""', block)
        self.assertIn('_recordatorios_log.warning("No se pudo leer tareas para recordatorios: %s", texto[:200])', block)
        self.assertIn('_recordatorios_log.error("Error consultando tareas para recordatorios: %s", e)', block)
        # Downstream push and mark-as-sent PATCH are outside this read-only cut.
        self.assertIn('await enviar_push(', block)
        self.assertIn('await c.patch(f"{SUPABASE_URL}/rest/v1/tareas"', block)
        read_end = block.index("    for t in tareas:")
        self.assertNotIn("/rest/v1/tareas", block[:read_end])


if __name__ == "__main__":
    unittest.main()
