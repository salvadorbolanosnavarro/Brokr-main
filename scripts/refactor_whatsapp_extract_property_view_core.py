"""Extract behavior-identical WhatsApp property presentation helpers.

Before editing whatsapp.py, compare executable AST bodies (ignoring only
function docstrings) with routers.whatsapp_property_view. The transform removes
exactly three top-level pure helpers and replaces them with one canonical import.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_property_view.py"
TARGETS = ("_texto_inmueble", "_fotos_a_imagenes", "_propiedad_para_ficha")
IMPORT = (
    "from routers.whatsapp_property_view import "
    "_fotos_a_imagenes, _propiedad_para_ficha, _texto_inmueble\n"
)


def _funcs(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    out: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in TARGETS:
            if node.name in out:
                raise SystemExit(f"duplicate property-view helper: {node.name}")
            out[node.name] = node
    return out


def _shape_without_docstring(node: ast.FunctionDef) -> str:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    clone = ast.FunctionDef(
        name=node.name,
        args=node.args,
        body=body,
        decorator_list=node.decorator_list,
        returns=node.returns,
        type_comment=node.type_comment,
        type_params=getattr(node, "type_params", []),
    )
    return ast.dump(clone, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = WHATSAPP.read_text(encoding="utf-8")
    if IMPORT.strip() in source:
        raise SystemExit("WhatsApp property view is already extracted")

    root_funcs = _funcs(ast.parse(source))
    canonical_funcs = _funcs(ast.parse(CANONICAL.read_text(encoding="utf-8")))
    missing_root = [name for name in TARGETS if name not in root_funcs]
    missing_canonical = [name for name in TARGETS if name not in canonical_funcs]
    if missing_root or missing_canonical:
        raise SystemExit(
            f"property-view source contract changed; root_missing={missing_root}, "
            f"canonical_missing={missing_canonical}"
        )

    mismatched = [
        name for name in TARGETS
        if _shape_without_docstring(root_funcs[name])
        != _shape_without_docstring(canonical_funcs[name])
    ]
    if mismatched:
        raise SystemExit(
            "property-view helpers differ; refusing extraction: " + ", ".join(mismatched)
        )

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

    remaining = _funcs(ast.parse(updated))
    if remaining:
        raise SystemExit(f"legacy property-view helpers survived: {sorted(remaining)}")
    if updated.count(IMPORT.strip()) != 1:
        raise SystemExit("canonical property-view import contract changed")

    WHATSAPP.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp property view helpers:", ", ".join(TARGETS))


if __name__ == "__main__":
    main()
