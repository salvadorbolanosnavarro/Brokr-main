#!/usr/bin/env python3
"""Extract WhatsApp media persistence helpers to the canonical Storage module.

Only two top-level async helpers are eligible. Their AST must match the
canonical implementations after normalizing the intentional public/private
function-name difference; otherwise the transform refuses to edit whatsapp.py.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_media_storage.py"
TARGETS = {
    "_guardar_archivo": "guardar_archivo",
    "_borrar_archivos": "borrar_archivos",
}
IMPORT_TEXT = (
    "from routers.whatsapp_media_storage import "
    "borrar_archivos as _borrar_archivos, guardar_archivo as _guardar_archivo\n"
)
CORE_STORAGE_NAMES = {"delete_objects", "upload_object"}


def functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def normalized_dump(node: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> str:
    cloned = copy.deepcopy(node)
    cloned.name = name
    return ast.dump(cloned, annotate_fields=True, include_attributes=False)


def insertion_line(tree: ast.Module) -> int:
    last_import_end = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last_import_end = max(last_import_end, node.end_lineno or node.lineno)
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and node is tree.body[0]
        ):
            continue
        if last_import_end:
            break
    if not last_import_end:
        raise SystemExit("refusing media extraction: no top-level import block found")
    return last_import_end


def core_storage_import(tree: ast.Module) -> ast.ImportFrom:
    matches = [
        node for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "core.storage"
    ]
    if len(matches) != 1:
        raise SystemExit(
            "refusing media extraction: expected exactly one core.storage import"
        )
    imported = {alias.asname or alias.name: alias.name for alias in matches[0].names}
    expected = {name: name for name in CORE_STORAGE_NAMES}
    if imported != expected:
        raise SystemExit(
            f"refusing media extraction: unexpected core.storage aliases {imported}"
        )
    return matches[0]


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fns = functions(source_tree)
    canonical_fns = functions(canonical_tree)

    missing_legacy = [legacy for legacy in TARGETS if legacy not in source_fns]
    missing_canonical = [canon for canon in TARGETS.values() if canon not in canonical_fns]
    if missing_legacy:
        raise SystemExit(f"refusing media extraction: missing legacy functions {missing_legacy}")
    if missing_canonical:
        raise SystemExit(f"refusing media extraction: missing canonical functions {missing_canonical}")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("refusing media extraction: canonical import already present")

    mismatched = []
    for legacy, canon in TARGETS.items():
        if normalized_dump(source_fns[legacy], canon) != normalized_dump(canonical_fns[canon], canon):
            mismatched.append(legacy)
    if mismatched:
        raise SystemExit(f"refusing media extraction: AST mismatch for {mismatched}")

    storage_import = core_storage_import(source_tree)
    target_lines: set[int] = set()
    for legacy in TARGETS:
        node = source_fns[legacy]
        if node.end_lineno is None:
            raise SystemExit(f"refusing media extraction: {legacy} lacks end_lineno")
        target_lines.update(range(node.lineno, node.end_lineno + 1))
    outside_storage_uses = [
        (node.id, node.lineno)
        for node in ast.walk(source_tree)
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in CORE_STORAGE_NAMES
            and node.lineno not in target_lines
        )
    ]
    if outside_storage_uses:
        raise SystemExit(
            "refusing media extraction: core.storage names used outside media helpers "
            f"{outside_storage_uses}"
        )

    lines = source.splitlines(keepends=True)
    remove_lines: set[int] = set()
    for legacy in TARGETS:
        node = source_fns[legacy]
        remove_lines.update(range(node.lineno, node.end_lineno + 1))
        if node.end_lineno < len(lines) and not lines[node.end_lineno].strip():
            remove_lines.add(node.end_lineno + 1)
    if storage_import.end_lineno is None:
        raise SystemExit("refusing media extraction: core.storage import lacks end_lineno")
    remove_lines.update(range(storage_import.lineno, storage_import.end_lineno + 1))

    insert_after = insertion_line(source_tree)
    output: list[str] = []
    inserted = False
    for lineno, line in enumerate(lines, start=1):
        if lineno not in remove_lines:
            output.append(line)
        if lineno == insert_after:
            output.append(IMPORT_TEXT)
            inserted = True
    if not inserted:
        raise SystemExit("refusing media extraction: failed to place canonical import")

    updated = "".join(output)
    updated_tree = ast.parse(updated, filename=str(SOURCE))
    updated_fns = functions(updated_tree)
    leftovers = [legacy for legacy in TARGETS if legacy in updated_fns]
    if leftovers:
        raise SystemExit(f"refusing media extraction: legacy functions remain {leftovers}")

    imports = [
        node for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_media_storage"
    ]
    if len(imports) != 1:
        raise SystemExit("refusing media extraction: expected exactly one media-storage import")
    aliases = {alias.asname: alias.name for alias in imports[0].names}
    expected = {legacy: canon for legacy, canon in TARGETS.items()}
    if aliases != expected:
        raise SystemExit(f"refusing media extraction: unexpected aliases {aliases}")
    if any(
        isinstance(node, ast.ImportFrom) and node.module == "core.storage"
        for node in updated_tree.body
    ):
        raise SystemExit("refusing media extraction: core.storage import remains in whatsapp.py")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp media storage helpers: " + ", ".join(TARGETS))


if __name__ == "__main__":
    main()
