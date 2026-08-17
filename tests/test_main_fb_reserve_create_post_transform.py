"""Dry-run guard for _fb_reservar_creacion POST Core routing."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_fb_reserve_create_post_core.py"

spec = importlib.util.spec_from_file_location("fb_reserve_create_post_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainFbReserveCreatePostTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.transformed = transform.transform_source(cls.source)

    def test_transform_is_exact_and_compiles(self):
        compile(self.transformed, "main.py", "exec")
        self.assertEqual(MAIN.read_text(encoding="utf-8"), self.source)
        self.assertEqual(self.transformed.count(transform.NEW), 1)
        self.assertNotIn(transform.OLD, self.transformed)
        if transform.OLD in self.source:
            self.assertEqual(self.source.count(transform.OLD), 1)
            self.assertEqual(self.transformed, self.source.replace(transform.OLD, transform.NEW, 1))
        else:
            self.assertEqual(self.source.count(transform.NEW), 1)
            self.assertEqual(self.transformed, self.source)

    def test_idempotency_and_fail_soft_contract_are_preserved(self):
        new = transform.NEW
        self.assertIn('filas = await post_rows(', new)
        self.assertIn('_FB_TABLA_ENTIDADES,', new)
        self.assertIn('fila,', new)
        self.assertIn('prefer="return=representation"', new)
        self.assertIn('timeout=10', new)
        self.assertIn('accepted_statuses=(200, 201)', new)
        self.assertIn('return {"modo": "nuevo", "row_id": (filas[0]["id"] if filas else fila["id"])}', new)
        self.assertIn('except httpx.HTTPStatusError as e:', new)
        self.assertIn('r = e.response', new)
        self.assertIn('if _fb_tabla_falta(r):', new)
        self.assertIn('_fb_avisa_migracion("reservar creación", r)', new)
        self.assertIn('if r.status_code == 409 and idempotency_key:', new)
        self.assertIn('previa = await _fb_buscar_por_idempotencia(user_id, idempotency_key)', new)
        self.assertIn('return {"modo": "duplicado", "row": previa}', new)
        self.assertIn('except Exception as e:', new)
        self.assertIn('return {"modo": "sin_tabla"}', self.transformed)
        self.assertNotIn('/rest/v1/', new)


if __name__ == "__main__":
    unittest.main()
