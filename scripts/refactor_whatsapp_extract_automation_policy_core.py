#!/usr/bin/env python3
"""Extract pure WhatsApp automation normalization behind a compatibility wrapper."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_automation_policy.py"
LEGACY = "_limpiar_automatizacion"
CORE = "_limpiar_automatizacion_core"
IMPORT_MODULE = "routers.whatsapp_automation_policy"
WRAPPER = '''def _limpiar_automatizacion(req: AutomatizacionReq) -> dict:\n    return _limpiar_automatizacion_core(\n        req, _AUTO_TIPOS=_AUTO_TIPOS, _FLUJO_CAMPOS=_FLUJO_CAMPOS,\n        HTTPException=HTTPException,\n    )\n'''
EXPECTED_KW = {"_AUTO_TIPOS", "_FLUJO_CAMPOS", "HTTPException"}


def _function(tree: ast.Module, name: str):
    matches = [node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise SystemExit(f"refusing automation-policy extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _body_shape(node) -> str:
    module = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.dump(module, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    legacy = _function(source_tree, LEGACY)
    core = _function(canonical_tree, CORE)
    if _body_shape(legacy) != _body_shape(core):
        raise SystemExit("refusing automation-policy extraction: executable bodies differ")

    lines = source.splitlines(keepends=True)
    if legacy.end_lineno is None:
        raise SystemExit("refusing automation-policy extraction: legacy helper lacks end_lineno")
    lines[legacy.lineno - 1:legacy.end_lineno] = [WRAPPER, "\n"]
    intermediate = "".join(lines)
    tree = ast.parse(intermediate, filename=str(SOURCE))

    existing = [node for node in tree.body
                if isinstance(node, ast.ImportFrom) and node.module == IMPORT_MODULE]
    if existing:
        raise SystemExit("WhatsApp automation policy is already imported")

    # Insert immediately before the compatibility wrapper to keep the cut bounded.
    wrapper = _function(tree, LEGACY)
    current = intermediate.splitlines(keepends=True)
    current[wrapper.lineno - 1:wrapper.lineno - 1] = [
        "from routers.whatsapp_automation_policy import _limpiar_automatizacion_core\n\n"
    ]
    updated = "".join(current)
    updated_tree = ast.parse(updated, filename=str(SOURCE))
    wrapper = _function(updated_tree, LEGACY)
    delegates = [call for call in ast.walk(wrapper)
                 if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                 and call.func.id == CORE]
    if len(delegates) != 1:
        raise SystemExit("refusing automation-policy extraction: wrapper delegate count differs")
    if {kw.arg for kw in delegates[0].keywords} != EXPECTED_KW:
        raise SystemExit("refusing automation-policy extraction: dependency contract differs")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp automation normalization policy")


if __name__ == "__main__":
    main()
