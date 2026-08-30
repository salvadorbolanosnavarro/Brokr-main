from __future__ import annotations

import ast
from pathlib import Path


MAIN = Path("main.py")
PREFIX = "core.facebook_"


def _bound_names(node: ast.ImportFrom) -> list[str]:
    return [alias.asname or alias.name for alias in node.names]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)

    loaded = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }

    candidates: list[ast.ImportFrom] = []
    removed_names: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or not node.module.startswith(PREFIX):
            continue
        names = _bound_names(node)
        if names and all(name not in loaded for name in names):
            candidates.append(node)
            removed_names.extend(names)

    if not candidates:
        raise SystemExit("no fully dead core.facebook_* imports found")

    # Keep the cut bounded: whole import declarations only, never partial edits.
    if len(candidates) > 12:
        raise SystemExit(f"unexpectedly broad facebook import cleanup: {len(candidates)} declarations")

    spans = sorted(
        ((node.lineno, node.end_lineno) for node in candidates),
        reverse=True,
    )
    lines = source.splitlines(keepends=True)
    for start, end in spans:
        del lines[start - 1 : end]

    updated = "".join(lines)
    ast.parse(updated)

    # Prove every removed binding had zero reads in the original AST.
    leaked = sorted(set(removed_names) & loaded)
    if leaked:
        raise SystemExit(f"refusing to remove live facebook bindings: {leaked}")

    MAIN.write_text(updated, encoding="utf-8")
    print(f"removed {len(candidates)} fully dead core.facebook_* import declarations")
    print("bindings:", ", ".join(sorted(removed_names)))


if __name__ == "__main__":
    main()
