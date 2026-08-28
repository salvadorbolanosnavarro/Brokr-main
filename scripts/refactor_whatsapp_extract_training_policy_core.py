#!/usr/bin/env python3
"""Extract behavior-identical WhatsApp training policy into its canonical module.

The transform verifies the TRAINING_DEFAULTS value and the executable AST of
four pure helpers before touching whatsapp.py. Function docstrings are ignored
because the canonical module intentionally uses shorter documentation while
preserving executable behavior exactly.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_training.py"
ASSIGNMENT = "TRAINING_DEFAULTS"
FUNCTIONS = (
    "_reglas_para_prompt",
    "_conocimiento_para_prompt",
    "_calificacion_para_prompt",
    "_en_horario",
)
IMPORT_TEXT = (
    "from routers.whatsapp_training import TRAINING_DEFAULTS, "
    "_calificacion_para_prompt, _conocimiento_para_prompt, _en_horario, "
    "_reglas_para_prompt\n"
)


def _assignment(tree: ast.Module, name: str) -> ast.Assign:
    matches = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == name:
            matches.append(node)
    if len(matches) != 1:
        raise SystemExit(f"refusing training-policy extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    out: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            if node.name in out:
                raise SystemExit(f"refusing training-policy extraction: duplicate {node.name}")
            out[node.name] = node
    missing = [name for name in FUNCTIONS if name not in out]
    if missing:
        raise SystemExit(f"refusing training-policy extraction: missing helpers {missing}")
    return out


def _without_docstring(node: ast.FunctionDef) -> ast.FunctionDef:
    cloned = copy.deepcopy(node)
    if (
        cloned.body
        and isinstance(cloned.body[0], ast.Expr)
        and isinstance(cloned.body[0].value, ast.Constant)
        and isinstance(cloned.body[0].value.value, str)
    ):
        cloned.body = cloned.body[1:]
    return cloned


def _shape(node: ast.AST) -> str:
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp training policy is already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_assignment = _assignment(source_tree, ASSIGNMENT)
    canonical_assignment = _assignment(canonical_tree, ASSIGNMENT)
    source_functions = _functions(source_tree)
    canonical_functions = _functions(canonical_tree)

    if _shape(source_assignment.value) != _shape(canonical_assignment.value):
        raise SystemExit("refusing training-policy extraction: TRAINING_DEFAULTS differs")

    mismatched = [
        name for name in FUNCTIONS
        if _shape(_without_docstring(source_functions[name]))
        != _shape(_without_docstring(canonical_functions[name]))
    ]
    if mismatched:
        raise SystemExit(
            "refusing training-policy extraction: helper AST differs: " + ", ".join(mismatched)
        )

    nodes: list[ast.AST] = [source_assignment, *source_functions.values()]
    spans: list[tuple[int, int]] = []
    for node in nodes:
        end = getattr(node, "end_lineno", None)
        if end is None:
            raise SystemExit("refusing training-policy extraction: node lacks end_lineno")
        spans.append((node.lineno, end))

    insert_at = source_assignment.lineno
    lines = source.splitlines(keepends=True)
    remove_lines: set[int] = set()
    for start, end in spans:
        remove_lines.update(range(start, end + 1))
        if end < len(lines) and not lines[end].strip():
            remove_lines.add(end + 1)

    output: list[str] = []
    inserted = False
    for lineno, line in enumerate(lines, start=1):
        if lineno == insert_at:
            output.append(IMPORT_TEXT)
            output.append("\n")
            inserted = True
        if lineno not in remove_lines:
            output.append(line)
    if not inserted:
        raise SystemExit("refusing training-policy extraction: failed to insert import")

    updated = "".join(output)
    updated_tree = ast.parse(updated, filename=str(SOURCE))

    try:
        _assignment(updated_tree, ASSIGNMENT)
    except SystemExit:
        pass
    else:
        raise SystemExit("refusing training-policy extraction: legacy TRAINING_DEFAULTS survived")

    surviving = {
        node.name for node in updated_tree.body
        if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS
    }
    if surviving:
        raise SystemExit(f"refusing training-policy extraction: legacy helpers survived {sorted(surviving)}")

    imports = [
        node for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_training"
    ]
    if len(imports) != 1:
        raise SystemExit("refusing training-policy extraction: expected one canonical import")
    names = {alias.name for alias in imports[0].names}
    expected = {ASSIGNMENT, *FUNCTIONS}
    if names != expected or any(alias.asname for alias in imports[0].names):
        raise SystemExit(f"refusing training-policy extraction: unexpected import contract {names}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp training policy: TRAINING_DEFAULTS, " + ", ".join(FUNCTIONS))


if __name__ == "__main__":
    main()
