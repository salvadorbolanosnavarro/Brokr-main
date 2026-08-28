"""Remove a bounded set of dead stdlib imports from main.py.

The cleanup is intentionally conservative: only the explicitly allow-listed
legacy names below are eligible, and a name is removed only when the AST proves
it is not loaded anywhere outside its own import statement. No anchor/text
search is used to decide liveness.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
TARGETS = {"logging", "hmac", "hashlib"}


def _loaded_names(tree: ast.AST) -> set[str]:
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)
    loaded = _loaded_names(tree)

    eligible = TARGETS - loaded
    if not eligible:
        raise SystemExit("no allow-listed dead stdlib imports remain")

    top_imports = [node for node in tree.body if isinstance(node, ast.Import)]
    imported_targets: set[str] = set()
    replacements: list[tuple[int, int, str]] = []

    for node in top_imports:
        if node.end_lineno is None:
            raise SystemExit("stdlib import source contract changed")
        names_here = {alias.asname or alias.name for alias in node.names}
        matched = names_here & eligible
        if not matched:
            continue
        imported_targets |= matched
        kept = [alias for alias in node.names if (alias.asname or alias.name) not in matched]
        if kept:
            rendered = "import " + ", ".join(
                alias.name + (f" as {alias.asname}" if alias.asname else "")
                for alias in kept
            ) + "\n"
        else:
            rendered = ""
        replacements.append((node.lineno, node.end_lineno, rendered))

    if not imported_targets:
        raise SystemExit(
            f"eligible dead names are not top-level imports: {sorted(eligible)}"
        )

    lines = source.splitlines(keepends=True)
    for start, end, rendered in sorted(replacements, reverse=True):
        lines[start - 1:end] = [rendered] if rendered else []
    updated = "".join(lines)

    final_tree = ast.parse(updated)
    final_loaded = _loaded_names(final_tree)
    if final_loaded != loaded:
        raise SystemExit("cleanup unexpectedly changed loaded-name set")

    remaining_imported = {
        alias.asname or alias.name
        for node in final_tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    leaked = imported_targets & remaining_imported
    if leaked:
        raise SystemExit(f"dead stdlib imports survived cleanup: {sorted(leaked)}")

    MAIN.write_text(updated, encoding="utf-8")
    print("removed dead stdlib imports:", ", ".join(sorted(imported_targets)))


if __name__ == "__main__":
    main()
