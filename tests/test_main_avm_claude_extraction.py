"""Regression guards for the prepared Claude AVM extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "avm_claude.py"
SCRIPT = ROOT / "scripts" / "refactor_main_extract_avm_claude_core.py"


class AvmClaudeExtractionPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_request_and_auth_contract_are_preserved(self):
        r = self.router
        self.assertIn('class AvmClaudeRequest(BaseModel):', r)
        self.assertIn('@router.post("/api/avm-claude")', r)
        self.assertEqual(r.count('get_user_id_from_token(request)'), 2)
        self.assertIn('exigir_cupo(request, _uid)', r)
        self.assertIn('exigir_sesion(request, _uid)', r)
        self.assertIn('raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada en el servidor")', r)

    def test_claude_call_telemetry_and_parse_contract_are_preserved(self):
        r = self.router
        self.assertIn('"model": "claude-sonnet-4-6"', r)
        self.assertIn('"max_tokens": 2000', r)
        self.assertIn('"temperature": 0.3', r)
        self.assertIn('async with httpx.AsyncClient(timeout=60) as client:', r)
        self.assertIn('raise HTTPException(status_code=502, detail=f"Error de Claude: {r.text[:300]}")', r)
        self.assertIn('_track_anthropic(user_id, "avm", "/api/avm-claude", _resp_json,', r)
        self.assertIn('resultado = _json.loads(raw)', r)
        self.assertIn('raise HTTPException(status_code=502, detail=f"Claude no devolvió JSON válido: {raw[:500]}")', r)
        self.assertIn('resultado["timestamp"] = time.strftime("%Y-%m-%d %H:%M")', r)
        self.assertIn('resultado["propiedad_descripcion"] =', r)

    def test_prompt_contract_keeps_exact_output_schema(self):
        r = self.router
        for key in (
            '"valor_estimado"', '"valor_minimo"', '"valor_maximo"',
            '"valor_por_m2_construccion"', '"valor_por_m2_terreno"',
            '"nivel_confianza"', '"razon_confianza"', '"resumen_ejecutivo"',
            '"analisis_ubicacion"', '"analisis_propiedad"',
            '"factores_positivos"', '"factores_negativos"', '"recomendaciones"',
            '"mercado_actual"', '"metodologia"', '"advertencias"',
        ):
            self.assertIn(key, r)

    def test_transform_is_bounded_and_files_compile(self):
        s = self.script
        self.assertIn('AVM — CLAUDE AI OPINION DE VALOR', s)
        self.assertIn('AVM — OPINIÓN DE VALOR CON INVESTIGACIÓN CONTROLADA DE COMPARABLES', s)
        self.assertIn('from routers.avm_claude import router as avm_claude_router', s)
        self.assertIn('compile(transformed, str(MAIN), "exec")', s)
        compile(self.router, "routers/avm_claude.py", "exec")
        compile(self.script, "scripts/refactor_main_extract_avm_claude_core.py", "exec")


if __name__ == "__main__":
    unittest.main()
