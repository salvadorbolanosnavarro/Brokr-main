from __future__ import annotations

import ast
from pathlib import Path

from core.firmas_policy import CONSENTIMIENTO, ROLES, TIPOS, TIPOS_CON_AGENTE


TARGET = Path("routers/firmas.py")
POLICY_MODULE = "core.firmas_policy"
TARGET_NAMES = ("TIPOS", "ROLES", "TIPOS_CON_AGENTE", "CONSENTIMIENTO")
EXPECTED_VALUES = {
    "TIPOS": TIPOS,
    "ROLES": ROLES,
    "TIPOS_CON_AGENTE": TIPOS_CON_AGENTE,
    "CONSENTIMIENTO": CONSENTIMIENTO,
}


def _assigned_name(node: ast.stmt) -> str | None:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assignments: dict[str, ast.Assign] = {}
    policy_imports: list[ast.ImportFrom] = []
    core_utils_import: ast.ImportFrom | None = None

    for node in tree.body:
        name = _assigned_name(node)
        if name in TARGET_NAMES:
            if name in assignments:
                raise SystemExit(f"duplicate Firmas policy assignment: {name}")
            assignments[name] = node
        if isinstance(node, ast.ImportFrom) and node.module == POLICY_MODULE:
            policy_imports.append(node)
        if isinstance(node, ast.ImportFrom) and node.module == "core.firmas_utils":
            if core_utils_import is not None:
                raise SystemExit("duplicate core.firmas_utils import")
            core_utils_import = node

    missing = sorted(set(TARGET_NAMES) - set(assignments))
    if missing:
        raise SystemExit(f"missing Firmas policy assignments: {missing}")
    if policy_imports:
        raise SystemExit("core.firmas_policy import already present")
    if core_utils_import is None:
        raise SystemExit("core.firmas_utils import missing")

    for name, node in assignments.items():
        try:
            actual = ast.literal_eval(node.value)
        except Exception as exc:
            raise SystemExit(f"Firmas policy assignment is not literal: {name}") from exc
        if actual != EXPECTED_VALUES[name]:
            raise SystemExit(f"Firmas policy literal drifted before extraction: {name}")

    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, int, list[str]]] = []
    for name in TARGET_NAMES:
        node = assignments[name]
        edits.append((node.lineno, node.end_lineno or node.lineno, []))

    import_line = (
        "from core.firmas_policy import CONSENTIMIENTO, ROLES, TIPOS, TIPOS_CON_AGENTE\n"
    )
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
        raise SystemExit(f"Firmas policy assignments remained in router: {sorted(remaining)}")

    imports_after = [
        node
        for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == POLICY_MODULE
    ]
    if len(imports_after) != 1:
        raise SystemExit(f"expected one core.firmas_policy import, found {len(imports_after)}")
    imported = {alias.asname or alias.name for alias in imports_after[0].names}
    if imported != set(TARGET_NAMES):
        raise SystemExit(f"unexpected Firmas policy imports: {sorted(imported)}")

    TARGET.write_text(updated, encoding="utf-8")
    print("extracted Firmas static vocabulary and consent policy")


if __name__ == "__main__":
    main()
