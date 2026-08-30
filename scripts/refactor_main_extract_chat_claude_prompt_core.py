from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
PROMPT_MODULE = ROOT / "routers" / "chat_claude_prompt.py"
TARGET = "SHAARK_SYSTEM_PROMPT"
IMPORT_LINE = "from routers.chat_claude_prompt import SHAARK_SYSTEM_PROMPT\n"


def _find_assignment(tree: ast.Module, *, where: str) -> ast.Assign:
    found: list[ast.Assign] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == TARGET:
            found.append(node)
    if len(found) != 1:
        raise SystemExit(f"expected exactly one {TARGET} assignment in {where}, found {len(found)}")
    return found[0]


def _string_value(node: ast.Assign, *, where: str) -> str:
    value = node.value
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        raise SystemExit(f"{TARGET} in {where} is not a literal string constant")
    return value.value


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    prompt_source = PROMPT_MODULE.read_text(encoding="utf-8")
    main_tree = ast.parse(source, filename=str(MAIN))
    prompt_tree = ast.parse(prompt_source, filename=str(PROMPT_MODULE))

    main_assign = _find_assignment(main_tree, where="main.py")
    prompt_assign = _find_assignment(prompt_tree, where="chat_claude_prompt.py")

    main_value = _string_value(main_assign, where="main.py")
    prompt_value = _string_value(prompt_assign, where="chat_claude_prompt.py")
    if main_value != prompt_value:
        raise SystemExit(
            f"literal mismatch for {TARGET}: main_len={len(main_value)} prompt_len={len(prompt_value)}"
        )

    for node in main_tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "routers.chat_claude_prompt":
            if any(alias.name == TARGET for alias in node.names):
                raise SystemExit("chat_claude_prompt import already present")

    if main_assign.end_lineno is None:
        raise SystemExit(f"missing end_lineno for {TARGET}")

    lines = source.splitlines(keepends=True)
    start = main_assign.lineno - 1
    end = main_assign.end_lineno
    del lines[start:end]
    lines.insert(start, IMPORT_LINE)

    updated = "".join(lines)
    ast.parse(updated, filename=str(MAIN))
    if updated == source:
        raise SystemExit("transform produced no change")
    MAIN.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
