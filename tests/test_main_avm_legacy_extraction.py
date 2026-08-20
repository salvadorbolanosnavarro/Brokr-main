"""Regression guards for the prepared legacy EasyBroker AVM extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "avm_legacy.py"
SCRIPT = ROOT / "scripts" / "refactor_main_extract_avm_legacy_core.py"


class LegacyAvmExtractionPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_public_contract_and_numeric_bounds_are_preserved(self):
        r = self.router
        self.assertIn('@router.post("/avm")', r)
        self.assertIn('50_000 <= v <= 999_000_000', r)
        self.assertIn('OP_MAP = {"venta": "sale", "renta": "rental"}', r)
        self.assertIn('while len(comparables) < 50 and page <= 160:', r)
        self.assertIn('median * 0.25 <= c["precio"] <= median * 4.0', r)
        self.assertIn('cache_set(cache_key, comparables[:30])', r)
        self.assertIn('APRECIACION_ANUAL = 0.04', r)
        self.assertIn('ANIO_ACTUAL = 2026', r)
        self.assertIn('(m2s / m2c) ** 0.5', r)
        self.assertIn('"malo": -0.15', r)
        self.assertIn('-0.015 * ((anos - 10) / 10)', r)

    def test_fallback_trimming_and_response_shape_are_preserved(self):
        r = self.router
        self.assertIn('if len(exact_matches) < 3 and req.tipo.lower() in TIPO_SIMILAR:', r)
        self.assertIn('if len(comparables_raw) < 3:', r)
        self.assertIn('if len(comparables_raw) < 2:', r)
        self.assertIn('status_code=422', r)
        self.assertIn('trim = max(1, n // 10)', r)
        self.assertIn('p_trim = precios[trim:n-trim] if n > 4 else precios', r)
        for key in (
            '"colonia": req.colonia', '"ciudad": req.ciudad', '"tipo": req.tipo',
            '"operacion": req.operacion', '"nivel": nivel', '"nivel_mensaje":',
            '"fuentes": ["EasyBroker"]', '"num_comparables": len(ajustados)',
            '"valor_minimo": valor_minimo', '"valor_probable": valor_probable',
            '"valor_maximo": valor_maximo', '"precio_m2_promedio": pm2_prom',
            '"comparables": ajustados[:10]', '"timestamp": time.strftime("%Y-%m-%d %H:%M")',
        ):
            self.assertIn(key, r)

    def test_prepared_router_matches_salient_legacy_contract_in_main(self):
        if '@app.post("/avm")' not in self.main:
            self.skipTest("legacy AVM already extracted")
        for needle in (
            '50_000 <= v <= 999_000_000',
            'APRECIACION_ANUAL = 0.04',
            'ANIO_ACTUAL = 2026',
            'trim    = max(1, n // 10)',
            '"valor_probable":     valor_probable',
            '"precio_m2_promedio": pm2_prom',
            '"comparables":        ajustados[:10]',
        ):
            self.assertIn(needle, self.main)

    def test_transform_is_bounded_and_files_compile(self):
        s = self.script
        self.assertIn('START = "# ────────────────────────────────────────────\\n# AVM — HELPERS', s)
        self.assertIn('END = "# ────────────────────────────────────────────\\n# AVM — CLAUDE AI OPINION DE VALOR', s)
        self.assertIn('from routers.avm_legacy import router as avm_legacy_router', s)
        self.assertIn('compile(transformed, str(MAIN), "exec")', s)
        compile(self.router, "routers/avm_legacy.py", "exec")
        compile(self.script, "scripts/refactor_main_extract_avm_legacy_core.py", "exec")


if __name__ == "__main__":
    unittest.main()
