#!/usr/bin/env python3
"""One-shot AST-bounded refactor of main.get_eb_key_for_user to Core DB."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "main.py"
FUNCTION = "get_eb_key_for_user"

NEW_FUNCTION = '''async def get_eb_key_for_user(user_id: str) -> str:
    # Acordado con Chava: la cuenta de EasyBroker es UNA por empresa, no por
    # agente. Buscamos por org_id para que todo el equipo use la misma.
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return None
    org_id = await get_org_id_for_user(user_id)
    if not org_id:
        return None
    try:
        rows = await get_rows(
            "user_integrations",
            {
                "org_id": f"eq.{org_id}",
                "provider": "eq.easybroker",
                "select": "api_key",
                "limit": "1",
            },
            timeout=8,
        )
        return (rows[0].get("api_key") or "").strip() or None if rows else None
    except Exception:
        return None
'''


def _function_span(source: str, name: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"expected one top-level async function {name}, found {len(matches)}")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: node.lineno - 1])
    end = sum(len(line) for line in lines[: node.end_lineno])
    return start, end, source[start:end]


def transform(source: str) -> str:
    start, end, old = _function_span(source, FUNCTION)
    if "/rest/v1/user_integrations" not in old:
        raise RuntimeError("target function no longer contains expected direct REST read")
    if "provider\": \"eq.easybroker" not in old:
        raise RuntimeError("target function no longer appears to be EasyBroker org-key lookup")
    updated = source[:start] + NEW_FUNCTION + source[end:]
    if updated.count("/rest/v1/user_integrations") != source.count("/rest/v1/user_integrations") - 1:
        raise RuntimeError("user_integrations REST references did not decrease exactly once")
    # The function remains fail-soft and organization-scoped.
    _, _, new = _function_span(updated, FUNCTION)
    for marker in (
        "org_id = await get_org_id_for_user(user_id)",
        '"provider": "eq.easybroker"',
        '"select": "api_key"',
        "except Exception:\n        return None",
    ):
        if marker not in new:
            raise RuntimeError(f"missing invariant after transform: {marker}")
    compile(updated, "main.py", "exec")
    return updated


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    updated = transform(source)
    if updated == source:
        raise RuntimeError("transform produced no change")
    TARGET.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
