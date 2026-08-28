#!/usr/bin/env python3
"""Move the WhatsApp AI brain behind a behavior-preserving compatibility wrapper.

The executable function body must match the canonical module exactly before the
transform edits whatsapp.py. Every global used by the legacy implementation is
injected by the wrapper, preserving runtime monkeypatch semantics.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_brain.py"
LEGACY = "recepcion2_responde"
CORE = "_recepcion2_responde_core"
IMPORT_TEXT = "from routers.whatsapp_brain import _recepcion2_responde_core\n"
WRAPPER = '''from routers.whatsapp_brain import _recepcion2_responde_core


async def recepcion2_responde(history: list, contexto: str, agente: dict, entren: dict) -> dict:
    return await _recepcion2_responde_core(
        history,
        contexto,
        agente,
        entren,
        TRAINING_DEFAULTS=TRAINING_DEFAULTS,
        _fmt_fecha_larga=_fmt_fecha_larga,
        _hora_local=_hora_local,
        _calificacion_para_prompt=_calificacion_para_prompt,
        _reglas_para_prompt=_reglas_para_prompt,
        _conocimiento_para_prompt=_conocimiento_para_prompt,
        httpx=httpx,
        asyncio=asyncio,
        json=json,
        ANTHROPIC_BASE=ANTHROPIC_BASE,
        ANTHROPIC_API_KEY=ANTHROPIC_API_KEY,
        WA2_MODEL=WA2_MODEL,
        log=log,
    )
'''


def _async_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    matches = [
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise SystemExit(f"refusing brain extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _body_shape(node: ast.AsyncFunctionDef) -> str:
    module = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.dump(module, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp AI brain is already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fn = _async_function(source_tree, LEGACY)
    canonical_fn = _async_function(canonical_tree, CORE)

    if _body_shape(source_fn) != _body_shape(canonical_fn):
        raise SystemExit("refusing brain extraction: canonical executable body differs from whatsapp.py")
    if source_fn.end_lineno is None:
        raise SystemExit("refusing brain extraction: legacy function lacks end_lineno")

    lines = source.splitlines(keepends=True)
    lines[source_fn.lineno - 1:source_fn.end_lineno] = [WRAPPER, "\n"]
    updated = "".join(lines)
    updated_tree = ast.parse(updated, filename=str(SOURCE))

    wrapper = _async_function(updated_tree, LEGACY)
    wrapper_calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
    if len(wrapper_calls) != 1:
        raise SystemExit("refusing brain extraction: compatibility wrapper has unexpected call count")
    call = wrapper_calls[0]
    if not isinstance(call.func, ast.Name) or call.func.id != CORE:
        raise SystemExit("refusing brain extraction: wrapper does not delegate to canonical core")

    imports = [
        node for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_brain"
    ]
    if len(imports) != 1:
        raise SystemExit("refusing brain extraction: expected one canonical import")
    aliases = [(alias.name, alias.asname) for alias in imports[0].names]
    if aliases != [(CORE, None)]:
        raise SystemExit(f"refusing brain extraction: unexpected import aliases {aliases}")

    expected_keywords = {
        "TRAINING_DEFAULTS", "_fmt_fecha_larga", "_hora_local",
        "_calificacion_para_prompt", "_reglas_para_prompt", "_conocimiento_para_prompt",
        "httpx", "asyncio", "json", "ANTHROPIC_BASE", "ANTHROPIC_API_KEY",
        "WA2_MODEL", "log",
    }
    actual_keywords = {kw.arg for kw in call.keywords}
    if actual_keywords != expected_keywords:
        raise SystemExit(f"refusing brain extraction: dependency contract differs {actual_keywords}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp AI brain behind compatibility wrapper")


if __name__ == "__main__":
    main()
