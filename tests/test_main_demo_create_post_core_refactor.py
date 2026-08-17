"""Permanent guard for demo scheduling persistence through Core."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainDemoCreatePostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/demo/agendar")')
        end = cls.source.index('\n\n@app.post("/subscription/cancel")', start)
        cls.block = cls.source[start:end]

    def test_demo_persistence_delegates_to_core_with_exact_statuses(self):
        block = self.block
        self.assertIn('await post_rows(', block)
        self.assertIn('"demos_agendadas"', block)
        self.assertIn('fila,', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=10', block)
        self.assertIn('accepted_statuses=(200, 201)', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('raise HTTPException(status_code=502, detail="No se pudo agendar. Intenta de nuevo en un momento.")', block)
        self.assertNotIn('/rest/v1/demos_agendadas', block)

    def test_email_notification_stays_after_successful_persistence(self):
        block = self.block
        db_pos = block.index('await post_rows(')
        email_pos = block.index('if _RESEND_KEY_DEMO:')
        self.assertLess(db_pos, email_pos)
        self.assertIn('https://api.resend.com/emails', block)
        self.assertIn('except Exception:\n            pass', block)
        self.assertIn('return {"ok": True}', block)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
