"""Deterministically move shared Facebook persistence compatibility helpers out of main.py."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
IMPORT_BLOCK = (
    "from core.facebook_persistence import (\n"
    "    FACEBOOK_AD_ENTITIES_TABLE as _FB_TABLA_ENTIDADES,\n"
    "    facebook_table_missing as _fb_tabla_falta,\n"
    "    warn_facebook_migration as _fb_avisa_migracion,\n"
    ")\n"
)
ASSIGNMENTS = {"_FB_TABLA_ENTIDADES", "_fb_aviso_tabla_dado"}
FUNCTIONS = {"_fb_tabla_falta", "_fb_avisa_migracion"}


def assignment_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assignment_nodes: dict[str, ast.Assign] = {}
    for name in ASSIGNMENTS:
        nodes = [n for n in tree.body if assignment_name(n) == name]
        if len(nodes) != 1:
            raise SystemExit(f"expected exactly one {name} assignment, found {len(nodes)}")
        assignment_nodes[name] = nodes[0]

    function_nodes: dict[str, ast.FunctionDef] = {}
    for name in FUNCTIONS:
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(nodes) != 1:
            raise SystemExit(f"expected exactly one {name} definition, found {len(nodes)}")
        function_nodes[name] = nodes[0]

    if ast.get_source_segment(source, assignment_nodes["_FB_TABLA_ENTIDADES"]) != '_FB_TABLA_ENTIDADES = "fb_ad_entities"':
        raise SystemExit("Facebook entities table assignment changed")
    if ast.get_source_segment(source, assignment_nodes["_fb_aviso_tabla_dado"]) != "_fb_aviso_tabla_dado = False":
        raise SystemExit("Facebook migration warning state changed")

    missing_source = ast.get_source_segment(source, function_nodes["_fb_tabla_falta"]) or ""
    warning_source = ast.get_source_segment(source, function_nodes["_fb_avisa_migracion"]) or ""
    for fragment in (
        "resp.status_code not in (404, 400)",
        '"does not exist" in texto',
        '"could not find the table" in texto',
        '"pgrst205" in texto',
    ):
        if fragment not in missing_source:
            raise SystemExit(f"missing-table behavior changed: {fragment}")
    for fragment in (
        "global _fb_aviso_tabla_dado",
        "if not _fb_aviso_tabla_dado:",
        "migracion-facebook-ads.sql",
        "Los anuncios se siguen creando sin ella.",
        "_fb_aviso_tabla_dado = True",
    ):
        if fragment not in warning_source:
            raise SystemExit(f"migration-warning behavior changed: {fragment}")

    required_consumers = (
        "_FB_TABLA_ENTIDADES,",
        "if _fb_tabla_falta(r):",
        '_fb_avisa_migracion("reservar creación", r)',
        '_fb_avisa_migracion("procesar lead", e.response)',
    )
    for fragment in required_consumers:
        if fragment not in source:
            raise SystemExit(f"Facebook persistence consumer changed: {fragment}")
    if "from core.facebook_persistence import" in source:
        raise SystemExit("Facebook persistence Core already imported")

    nodes_to_remove: list[ast.AST] = [*assignment_nodes.values(), *function_nodes.values()]
    lines = source.splitlines(keepends=True)
    spans = [(node.lineno - 1, node.end_lineno) for node in nodes_to_remove if node.end_lineno is not None]
    if len(spans) != 4:
        raise SystemExit("could not resolve all Facebook persistence spans")
    for start, end in sorted(spans, reverse=True):
        del lines[start:end]
    transformed = "".join(lines)

    tree2 = ast.parse(transformed)
    app_assignments = [
        n for n in tree2.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "FastAPI"
    ]
    if len(app_assignments) != 1:
        raise SystemExit(f"expected exactly one app = FastAPI(), found {len(app_assignments)}")
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_assignments[0].lineno - 1, "\n" + IMPORT_BLOCK)
    transformed = "".join(lines)

    check = ast.parse(transformed)
    leftovers = [assignment_name(n) for n in check.body if assignment_name(n) in ASSIGNMENTS]
    leftovers += [n.name for n in check.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    if leftovers:
        raise SystemExit(f"Facebook persistence legacy definitions remain: {leftovers}")
    if transformed.count("from core.facebook_persistence import (") != 1:
        raise SystemExit("unexpected Facebook persistence Core import count")
    for fragment in required_consumers:
        if fragment not in transformed:
            raise SystemExit(f"Facebook persistence consumer lost: {fragment}")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted Facebook persistence compatibility core")


if __name__ == "__main__":
    main()
