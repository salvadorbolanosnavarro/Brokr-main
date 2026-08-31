from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "avm_claude.py"


class AvmClaudeExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_and_request_model_are_isolated_from_main(self):
        self.assertIn('class AvmClaudeRequest(BaseModel):', self.router)
        self.assertIn('@router.post("/api/avm-claude")', self.router)
        self.assertIn('async def avm_claude(req: AvmClaudeRequest, request: Request):', self.router)
        self.assertNotIn('class AvmClaudeRequest(BaseModel):', self.main)
        self.assertNotIn('@app.post("/api/avm-claude")', self.main)
        self.assertNotIn('async def avm_claude(req: AvmClaudeRequest, request: Request):', self.main)
        self.assertIn('from routers.avm_claude import router as avm_claude_router', self.main)
        self.assertIn('app.include_router(avm_claude_router)', self.main)

    def test_auth_and_usage_guards_are_preserved(self):
        r = self.router
        self.assertIn('_uid = await get_user_id_from_token(request)', r)
        self.assertIn('exigir_cupo(request, _uid)', r)
        self.assertIn('exigir_sesion(request, _uid)', r)
        self.assertIn('if not ANTHROPIC_API_KEY:', r)
        self.assertIn('ANTHROPIC_API_KEY no configurada en el servidor', r)

    def test_anthropic_request_and_telemetry_contract_are_preserved(self):
        r = self.router
        self.assertIn('async with httpx.AsyncClient(timeout=60) as client:', r)
        self.assertIn('f"{ANTHROPIC_BASE}/messages"', r)
        self.assertIn('"anthropic-version": "2023-06-01"', r)
        self.assertIn('"model": "claude-sonnet-4-6"', r)
        self.assertIn('"max_tokens": 2000', r)
        self.assertIn('"temperature": 0.3', r)
        self.assertIn('_track_anthropic(user_id, "avm", "/api/avm-claude", _resp_json,', r)
        self.assertIn('raise HTTPException(status_code=502, detail=f"Error de Claude: {r.text[:300]}")', r)
        self.assertIn('raise HTTPException(status_code=502, detail=f"Claude no devolvió JSON válido: {raw[:500]}")', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/avm_claude.py", "exec")


if __name__ == "__main__":
    unittest.main()
