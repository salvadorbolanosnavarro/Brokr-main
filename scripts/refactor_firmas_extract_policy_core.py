from __future__ import annotations

import ast
from pathlib import Path


TARGET = Path("routers/firmas.py")
POLICY_PATH = Path("core/firmas_policy.py")
POLICY_MODULE = "core.firmas_policy"
TARGET_NAMES = ("TIPOS", "ROLES", "TIPOS_CON_AGENTE")
LEGAL_INLINE_NAME = "CONSENTIMIENTO"


def _assigned_name(node: ast.stmt) -> str | None:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _literal_assignments(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for node in tree.body:
        name = _assigned_name(node)
        if name not in TARGET_NAMES:
            continue
        if name in values:
            raise SystemExit(f"duplicate Firmas vocabulary assignment in {path}: {name}")
        try:
            values[name] = ast.literal_eval(node.value)
        except Exception as exc:
            raise SystemExit(f"Firmas vocabulary assignment is not literal in {path}: {name}") from exc
    missing = sorted(set(TARGET_NAMES) - set(values))
    if missing:
        raise SystemExit(f"missing Firmas vocabulary assignments in {path}: {missing}")
    return values


def main() -> None:
    expected_values = _literal_assignments(POLICY_PATH)
    source = TARGET.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assignments: dict[str, ast.Assign] = {}
    legal_inline: ast.Assign | None = None
    policy_imports: list[ast.ImportFrom] = []
    core_utils_import: ast.ImportFrom | None = None

    for node in tree.body:
        name = _assigned_name(node)
        if name in TARGET_NAMES:
            if name in assignments:
                raise SystemExit(f"duplicate Firmas vocabulary assignment: {name}")
            assignments[name] = node
        if name == LEGAL_INLINE_NAME:
            if legal_inline is not None:
                raise SystemExit("duplicate inline CONSENTIMIENTO assignment")
            legal_inline = node
        if isinstance(node, ast.ImportFrom) and node.module == POLICY_MODULE:
            policy_imports.append(node)
        if isinstance(node, ast.ImportFrom) and node.module == "core.firmas_utils":
            if core_utils_import is not None:
                raise SystemExit("duplicate core.firmas_utils import")
            core_utils_import = node

    missing = sorted(set(TARGET_NAMES) - set(assignments))
    if missing:
        raise SystemExit(f"missing Firmas vocabulary assignments: {missing}")
    if legal_inline is None:
        raise SystemExit("inline CONSENTIMIENTO legal invariant is missing")
    if policy_imports:
        raise SystemExit("core.firmas_policy import already present")
    if core_utils_import is None:
        raise SystemExit("core.firmas_utils import missing")

    for name, node in assignments.items():
        try:
            actual = ast.literal_eval(node.value)
        except Exception as exc:
            raise SystemExit(f"Firmas vocabulary assignment is not literal: {name}") from exc
        if actual != expected_values[name]:
            raise SystemExit(f"Firmas vocabulary literal drifted before extraction: {name}")

    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, int, list[str]]] = []
    for name in TARGET_NAMES:
        node = assignments[name]
        edits.append((node.lineno, node.end_lineno or node.lineno, []))

    import_line = "from core.firmas_policy import ROLES, TIPOS, TIPOS_CON_AGENTE\n"
    insertion_line = core_utils_import.end_lineno or core_utils_import.lineno
    edits.append((insertion_line + 1, insertion_line, [import_line]))

    for start, end, replacement in sorted(edits, reverse=True):
        lines[start - 1 : end] = replacement

    updated = "".join(lines)
    updated_tree = ast.parse(updated)

    remaining = {
        _assigned_name(node)
        for node in updated_tree.body
        if _assigned_name(node) in TARGET_NAMES
    }
    if remaining:
        raise SystemExit(f"Firmas vocabulary assignments remained in router: {sorted(remaining)}")
    if not any(_assigned_name(node) == LEGAL_INLINE_NAME for node in updated_tree.body):
        raise SystemExit("inline CONSENTIMIENTO was removed unexpectedly")

    imports_after = [
        node
        for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == POLICY_MODULE
    ]
    if len(imports_after) != 1:
        raise SystemExit(f"expected one core.firmas_policy import, found {len(imports_after)}")
    imported = {alias.asname or alias.name for alias in imports_after[0].names}
    if imported != set(TARGET_NAMES):
        raise SystemExit(f"unexpected Firmas vocabulary imports: {sorted(imported)}")

    TARGET.write_text(updated, encoding="utf-8")
    print("extracted Firmas static vocabulary; kept legal consent inline")


if __name__ == "__main__":
    main()
