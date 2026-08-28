"""Extract behavior-identical Meta Cloud API transport helpers from whatsapp.py.

This transform is deliberately self-verifying. Before editing the monolith it
parses routers.whatsapp_cloud_api and requires every targeted root helper to be
AST-identical to its canonical counterpart. Only then are the legacy top-level
definitions removed and replaced by explicit imports.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_cloud_api.py"
TARGETS = (
    "_revisar_token",
    "_retryable_status",
    "_espera_reintento",
    "_send_text_detallado",
    "_send_text",
    "_send_template",
    "_marcar_leido",
    "_descargar_media",
    "_send_image",
    "_send_document_link",
    "_send_document",
)
IMPORT = (
    "from routers.whatsapp_cloud_api import (\n"
    "    _descargar_media, _espera_reintento, _marcar_leido, _revisar_token,\n"
    "    _retryable_status, _send_document, _send_document_link, _send_image,\n"
    "    _send_template, _send_text, _send_text_detallado,\n"
    ")\n"
)


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in TARGETS:
            if node.name in out:
                raise SystemExit(f"duplicate target function: {node.name}")
            out[node.name] = node
    return out


def _shape(node: ast.AST) -> str:
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = WHATSAPP.read_text(encoding="utf-8")
    canonical_source = CANONICAL.read_text(encoding="utf-8")
    if "from routers.whatsapp_cloud_api import (" in source:
        raise SystemExit("WhatsApp Cloud API helpers are already extracted")

    root_tree = ast.parse(source)
    canonical_tree = ast.parse(canonical_source)
    root_funcs = _functions(root_tree)
    canonical_funcs = _functions(canonical_tree)

    missing_root = [name for name in TARGETS if name not in root_funcs]
    missing_canonical = [name for name in TARGETS if name not in canonical_funcs]
    if missing_root or missing_canonical:
        raise SystemExit(
            f"Cloud API source contract changed; root_missing={missing_root}, "
            f"canonical_missing={missing_canonical}"
        )

    mismatched = [
        name for name in TARGETS
        if _shape(root_funcs[name]) != _shape(canonical_funcs[name])
    ]
    if mismatched:
        raise SystemExit(
            "Cloud API helpers are not behavior-identical; refusing extraction: "
            + ", ".join(mismatched)
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
        replacement = [IMPORT, "\n"] if start == first_start else []
        lines[start - 1:end] = replacement
    updated = "".join(lines)

    final_tree = ast.parse(updated)
    final_funcs = _functions(final_tree)
    if final_funcs:
        raise SystemExit(f"legacy Cloud API helpers survived: {sorted(final_funcs)}")
    if updated.count("from routers.whatsapp_cloud_api import (") != 1:
        raise SystemExit("canonical Cloud API import contract changed")

    WHATSAPP.write_text(updated, encoding="utf-8")
    print("extracted AST-identical WhatsApp Cloud API helpers:", ", ".join(TARGETS))


if __name__ == "__main__":
    main()
