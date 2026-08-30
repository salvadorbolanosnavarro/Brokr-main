from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def _bound_names(node: ast.stmt) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.asname or alias.name.split(".", 1)[0] for alias in node.names}
    if isinstance(node, ast.ImportFrom):
        return {alias.asname or alias.name for alias in node.names if alias.name != "*"}
    return set()


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))

    playwright_nodes = [
        node for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "playwright.async_api"
        and [(a.name, a.asname) for a in node.names] == [("async_playwright", None)]
    ]
    if len(playwright_nodes) != 1:
        raise SystemExit(f"expected one async_playwright import, found {len(playwright_nodes)}")
    anchor = playwright_nodes[0]

    following = [node for node in tree.body if node.lineno > anchor.lineno]
    expected = []
    for node in following:
        if isinstance(node, ast.Import) and [(a.name, a.asname) for a in node.names] == [("base64", None), ("asyncio", None)]:
            expected.append(node)
        elif isinstance(node, ast.ImportFrom) and node.module == "pydantic" and [(a.name, a.asname) for a in node.names] == [("BaseModel", None)]:
            expected.append(node)
        elif isinstance(node, ast.ImportFrom) and node.module == "typing" and [(a.name, a.asname) for a in node.names] == [("List", None), ("Optional", None)]:
            expected.append(node)
        elif isinstance(node, ast.Import) and [(a.name, a.asname) for a in node.names] == [("os", None)]:
            expected.append(node)

    # The local os import appears immediately before the Playwright anchor; collect it separately.
    os_after_contracts = [
        node for node in tree.body
        if isinstance(node, ast.Import)
        and [(a.name, a.asname) for a in node.names] == [("os", None)]
        and node.lineno < anchor.lineno
    ]
    if len(os_after_contracts) < 2:
        raise SystemExit("expected duplicate os import before PDF block")
    local_os = os_after_contracts[-1]

    targets = [local_os]
    for predicate_name, predicate in (
        ("base64_asyncio", lambda n: isinstance(n, ast.Import) and [(a.name, a.asname) for a in n.names] == [("base64", None), ("asyncio", None)]),
        ("BaseModel", lambda n: isinstance(n, ast.ImportFrom) and n.module == "pydantic" and [(a.name, a.asname) for a in n.names] == [("BaseModel", None)]),
        ("List_Optional", lambda n: isinstance(n, ast.ImportFrom) and n.module == "typing" and [(a.name, a.asname) for a in n.names] == [("List", None), ("Optional", None)]),
    ):
        matches = [n for n in following if predicate(n)]
        if len(matches) != 1:
            raise SystemExit(f"expected one local {predicate_name} import, found {len(matches)}")
        targets.append(matches[0])

    earliest_target = min(node.lineno for node in targets)
    bound_before: set[str] = set()
    for node in tree.body:
        if node.lineno >= earliest_target:
            break
        bound_before.update(_bound_names(node))
    required = {"os", "base64", "asyncio", "BaseModel", "List", "Optional"}
    missing = sorted(required - bound_before)
    if missing:
        raise SystemExit(f"imports are not redundant; missing earlier bindings: {missing}")

    lines = source.splitlines(keepends=True)
    for node in sorted(targets, key=lambda n: n.lineno, reverse=True):
        if node.end_lineno is None:
            raise SystemExit("missing end_lineno")
        del lines[node.lineno - 1:node.end_lineno]

    updated = "".join(lines)
    ast.parse(updated, filename=str(MAIN))
    if updated == source:
        raise SystemExit("transform produced no change")
    MAIN.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
