"""Extract behavior-identical WhatsApp auth/visibility helpers.

The transform compares executable AST bodies (ignoring only docstrings) against
routers.whatsapp_access before touching the monolith, then replaces the two
legacy definitions with one canonical import.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_access.py"
TARGETS = ("_require_user", "_ids_visibles")
IMPORT = "from routers.whatsapp_access import _ids_visibles, _require_user\n"


def _funcs(tree: ast.Module) -> dict[str, ast.AsyncFunctionDef]:
    out: dict[str, ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name in TARGETS:
            if node.name in out:
                raise SystemExit(f"duplicate access helper: {node.name}")
            out[node.name] = node
    return out


def _executable_shape(node: ast.AsyncFunctionDef) -> str:
    clone = ast.AsyncFunctionDef(
        name=node.name,
        args=node.args,
        body=list(node.body),
        decorator_list=node.decorator_list,
        returns=node.returns,
        type_comment=node.type_comment,
        type_params=getattr(node, "type_params", []),
    )
    if (
        clone.body
        and isinstance(clone.body[0], ast.Expr)
        and isinstance(clone.body[0].value, ast.Constant)
        and isinstance(clone.body[0].value.value, str)
    ):
        clone.body = clone.body[1:]
    return ast.dump(clone, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = WHATSAPP.read_text(encoding="utf-8")
    if IMPORT.strip() in source:
        raise SystemExit("WhatsApp access helpers are already extracted")

    root_funcs = _funcs(ast.parse(source))
    canonical_funcs = _funcs(ast.parse(CANONICAL.read_text(encoding="utf-8")))
    missing_root = [name for name in TARGETS if name not in root_funcs]
    missing_canonical = [name for name in TARGETS if name not in canonical_funcs]
    if missing_root or missing_canonical:
        raise SystemExit(
            f"access source contract changed; root_missing={missing_root}, "
            f"canonical_missing={missing_canonical}"
        )
    mismatched = [
        name for name in TARGETS
        if _executable_shape(root_funcs[name]) != _executable_shape(canonical_funcs[name])
    ]
    if mismatched:
        raise SystemExit("access helpers differ; refusing extraction: " + ", ".join(mismatched))

    spans: list[tuple[int, int]] = []
    for name in TARGETS:
        node = root_funcs[name]
        if node.end_lineno is None:
            raise SystemExit(f"missing end_lineno for {name}")
        spans.append((node.lineno, node.end_lineno))

    first_start = min(start for start, _ in spans)
    lines = source.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        lines[start - 1:end] = [IMPORT, "\n"] if start == first_start else []
    updated = "".join(lines)
    if _funcs(ast.parse(updated)):
        raise SystemExit("legacy access helpers survived")
    if updated.count(IMPORT.strip()) != 1:
        raise SystemExit("canonical access import contract changed")

    WHATSAPP.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp access helpers:", ", ".join(TARGETS))


if __name__ == "__main__":
    main()
