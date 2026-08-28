"""Deterministically extract POST /chat-claude from main.py.

This transform is static only. It never imports the application or invokes the
Claude endpoint. The large legacy system prompt remains in main.py byte-for-byte
for this cut and is resolved dynamically by the prepared router.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

ROUTER_IMPORT = "from routers.chat_claude import create_router as create_chat_claude_router\n"
ROUTER_INCLUDE = '''app.include_router(create_chat_claude_router(lambda: {
    "get_user_id_from_token": get_user_id_from_token,
    "exigir_cupo": exigir_cupo,
    "exigir_sesion": exigir_sesion,
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    "ANTHROPIC_BASE": ANTHROPIC_BASE,
    "_request_modulo": _request_modulo,
    "_track_anthropic": _track_anthropic,
    "SHAARK_SYSTEM_PROMPT": SHAARK_SYSTEM_PROMPT,
}))
'''
REMOVE_NAMES = {"ClaudeChatRequest", "chat_claude_proxy"}


def node_name(node: ast.AST) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    return None


def node_start_lineno(node: ast.AST) -> int:
    start = node.lineno
    decorators = getattr(node, "decorator_list", None) or []
    if decorators:
        start = min([start, *(decorator.lineno for decorator in decorators)])
    return start


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")

    if "create_chat_claude_router" in source:
        raise SystemExit("Claude chat router already connected")
    if '@app.post("/chat-claude")' not in source:
        raise SystemExit("Claude chat route not found")
    if "SHAARK_SYSTEM_PROMPT" not in source:
        raise SystemExit("Claude system prompt contract changed")

    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    spans: list[tuple[int, int]] = []
    found: set[str] = set()

    for node in tree.body:
        name = node_name(node)
        if name not in REMOVE_NAMES:
            continue
        if node.end_lineno is None:
            raise SystemExit(f"Missing end_lineno for {name}")
        spans.append((node_start_lineno(node) - 1, node.end_lineno))
        found.add(name)

    missing = REMOVE_NAMES - found
    if missing:
        raise SystemExit(f"Claude chat source contract changed; missing: {sorted(missing)}")

    for start, end in sorted(spans, reverse=True):
        del lines[start:end]
    updated = "".join(lines)

    app_marker = "app = FastAPI()\n"
    if app_marker not in updated:
        raise SystemExit("FastAPI app marker changed")

    updated = updated.replace(
        app_marker,
        ROUTER_IMPORT + app_marker + ROUTER_INCLUDE,
        1,
    )

    if '@app.post("/chat-claude")' in updated:
        raise SystemExit("Claude chat route still present after extraction")
    if "class ClaudeChatRequest(" in updated:
        raise SystemExit("Claude chat request model still present after extraction")
    if "async def chat_claude_proxy(" in updated:
        raise SystemExit("Claude chat function still present after extraction")
    if "SHAARK_SYSTEM_PROMPT" not in updated:
        raise SystemExit("Claude system prompt moved unexpectedly")
    if ROUTER_IMPORT.strip() not in updated or ROUTER_INCLUDE.strip() not in updated:
        raise SystemExit("Claude chat router wiring missing after extraction")

    ast.parse(updated)
    MAIN.write_text(updated, encoding="utf-8")
    print("extracted POST /chat-claude")


if __name__ == "__main__":
    main()
