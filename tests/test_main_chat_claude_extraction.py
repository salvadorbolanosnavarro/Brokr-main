"""Permanent guards for static extraction of POST /chat-claude."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "chat_claude.py"
TRANSFORM = ROOT / "scripts" / "refactor_main_extract_chat_claude_core.py"


class ChatClaudeExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.transform = TRANSFORM.read_text(encoding="utf-8")

    def test_route_moves_as_one_bounded_unit(self):
        route_in_main = '@app.post("/chat-claude")' in self.main
        router_imported = (
            "from routers.chat_claude import create_router as create_chat_claude_router"
            in self.main
        )
        router_included = "app.include_router(create_chat_claude_router(" in self.main

        # Accept exactly the two deliberate workflow states: prepared or certified.
        self.assertEqual(router_imported, router_included)
        self.assertNotEqual(route_in_main, router_imported)
        self.assertEqual("class ClaudeChatRequest(" in self.main, route_in_main)
        self.assertEqual("async def chat_claude_proxy(" in self.main, route_in_main)
        self.assertIn('@router.post("/chat-claude")', self.router)

    def test_legacy_request_and_response_shape_are_preserved(self):
        router = self.router
        self.assertIn("messages: list", router)
        self.assertIn("max_tokens: int = 1200", router)
        self.assertIn('context: str = ""', router)
        self.assertIn('"choices": [{', router)
        self.assertIn('"role": "assistant"', router)
        self.assertIn('text = "Sin respuesta."', router)

    def test_auth_quota_telemetry_and_error_semantics_are_preserved(self):
        router = self.router
        self.assertIn("uid = await get_user_id_from_token(request)", router)
        self.assertIn("exigir_cupo(request, uid)", router)
        self.assertIn("exigir_sesion(request, uid)", router)
        self.assertIn('status_code=500, detail="ANTHROPIC_API_KEY no configurada"', router)
        self.assertGreaterEqual(router.count("await get_user_id_from_token(request)"), 2)
        self.assertIn('status_code=401, detail="No autenticado"', router)
        self.assertIn('(request_modulo(request) or "chat").lower()', router)
        self.assertIn("await track_anthropic(request, modulo)", router)

    def test_anthropic_payload_and_message_filter_are_preserved(self):
        router = self.router
        self.assertIn('isinstance(msg, dict) and msg.get("role") != "system"', router)
        self.assertIn('"model": "claude-sonnet-4-6"', router)
        self.assertIn('"max_tokens": min(req.max_tokens, 4096)', router)
        self.assertIn('"type": "web_search_20250305"', router)
        self.assertIn('"name": "web_search"', router)
        self.assertIn('"max_uses": 3', router)
        self.assertIn("httpx.AsyncClient(timeout=60.0)", router)
        self.assertIn('"anthropic-version": "2023-06-01"', router)
        self.assertIn('text += block.get("text", "")', router)

    def test_prompt_remains_single_source_in_main_for_this_cut(self):
        self.assertIn("SHAARK_SYSTEM_PROMPT", self.main)
        self.assertNotIn("Eres BROQ — el agente operativo", self.router)
        self.assertIn('deps["SHAARK_SYSTEM_PROMPT"]', self.router)
        self.assertIn('"SHAARK_SYSTEM_PROMPT": SHAARK_SYSTEM_PROMPT', self.transform)

    def test_transform_is_ast_bounded_and_removes_only_route_unit(self):
        self.assertIn("import ast", self.transform)
        self.assertIn('REMOVE_NAMES = {"ClaudeChatRequest", "chat_claude_proxy"}', self.transform)
        self.assertNotIn("anchor", self.transform.lower())
        self.assertIn("ast.parse(updated)", self.transform)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/chat_claude.py", "exec")
        compile(self.transform, "scripts/refactor_main_extract_chat_claude_core.py", "exec")


if __name__ == "__main__":
    unittest.main()
