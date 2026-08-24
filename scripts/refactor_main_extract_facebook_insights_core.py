#!/usr/bin/env python3
"""Move shared Facebook insights constants/normalizer out of main.py via bounded AST edits."""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ASSIGNMENTS = {"_FB_DATE_PRESETS", "_FB_BREAKDOWNS", "_FB_ACCIONES_CLAVE", "_FB_INSIGHTS_FIELDS"}
FUNCTION = "_fb_normaliza_insights"
EXPORTED = ASSIGNMENTS | {FUNCTION}
IMPORT = (
    "from core.facebook_insights import (\n"
    "    FB_BREAKDOWNS as _FB_BREAKDOWNS,\n"
    "    FB_DATE_PRESETS as _FB_DATE_PRESETS,\n"
    "    FB_INSIGHTS_FIELDS as _FB_INSIGHTS_FIELDS,\n"
    "    FB_KEY_ACTIONS as _FB_ACCIONES_CLAVE,\n"
    "    normalize_facebook_insights as _fb_normaliza_insights,\n"
    ")\n"
)


def assigned_names(node: ast.AST) -> set[str]:
    if not isinstance(node, ast.Assign):
        return set()
    return {t.id for t in node.targets if isinstance(t, ast.Name)}


def loaded_counts(nodes: list[ast.AST]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for node in nodes:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load) and child.id in EXPORTED:
                counts[child.id] += 1
    return counts


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body
    selected: list[ast.AST] = []
    for name in ASSIGNMENTS:
        matches = [node for node in body if name in assigned_names(node)]
        if len(matches) != 1:
            raise RuntimeError(f"expected one assignment for {name}, found {len(matches)}")
        selected.append(matches[0])
    funcs = [node for node in body if isinstance(node, ast.FunctionDef) and node.name == FUNCTION]
    if len(funcs) != 1:
        raise RuntimeError(f"expected one {FUNCTION}, found {len(funcs)}")
    selected.append(funcs[0])

    block = "\n".join(ast.get_source_segment(source, node) or "" for node in selected)
    for fragment in (
        '"last_7d"',
        '"publisher_platform"',
        '"onsite_conversion.messaging_conversation_started_7d": "conversaciones"',
        '"leadgen_grouped": "leads_formulario"',
        "actions,cost_per_action_type,objective,date_start,date_stop",
        "if not isinstance(item, dict)",
        "except (TypeError, ValueError)",
        'out["engagement"]',
    ):
        if fragment not in block:
            raise RuntimeError(f"missing expected insights behavior: {fragment}")
    if IMPORT.strip() in source:
        raise RuntimeError("Facebook insights Core import already present")

    apps = [node for node in body if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "app" for t in node.targets)
            and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "FastAPI"]
    if len(apps) != 1:
        raise RuntimeError(f"expected one app = FastAPI(), found {len(apps)}")
    ids = {id(node) for node in selected}
    before = loaded_counts([node for node in body if id(node) not in ids])

    lines = source.splitlines(keepends=True)
    edits = []
    for node in selected:
        if node.end_lineno is None:
            raise RuntimeError("selected AST node missing end_lineno")
        edits.append((node.lineno - 1, node.end_lineno, []))
    edits.append((apps[0].lineno - 1, apps[0].lineno - 1, [IMPORT, "\n"]))
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        lines[start:end] = replacement
    transformed = "".join(lines)
    out_tree = ast.parse(transformed, filename=str(MAIN))
    for name in ASSIGNMENTS:
        if any(name in assigned_names(node) for node in out_tree.body):
            raise RuntimeError(f"{name} assignment remains in main.py")
    if any(isinstance(node, ast.FunctionDef) and node.name == FUNCTION for node in out_tree.body):
        raise RuntimeError(f"{FUNCTION} remains in main.py")
    if transformed.count("from core.facebook_insights import (") != 1:
        raise RuntimeError("Facebook insights Core import count mismatch")
    after = loaded_counts(out_tree.body)
    for name in EXPORTED:
        if after[name] != before[name]:
            raise RuntimeError(f"external caller count changed for {name}: before={before[name]} after={after[name]}")
    if transformed == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted Facebook insights core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
