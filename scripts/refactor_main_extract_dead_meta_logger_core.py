from __future__ import annotations

import ast
from pathlib import Path


MAIN = Path("main.py")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)

    fb_log_assignments = []
    logging_import = None
    logging_loads = []
    fb_log_loads = []

    for node in tree.body:
        if isinstance(node, ast.Import) and [(a.name, a.asname) for a in node.names] == [("logging", None)]:
            if logging_import is not None:
                raise SystemExit("multiple top-level logging imports")
            logging_import = node
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_fb_log"
        ):
            fb_log_assignments.append(node)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id == "logging":
                logging_loads.append(node)
            elif node.id == "_fb_log":
                fb_log_loads.append(node)

    if logging_import is None:
        raise SystemExit("expected exact top-level import logging")
    if len(fb_log_assignments) != 1:
        raise SystemExit(f"expected one _fb_log assignment, found {len(fb_log_assignments)}")
    if fb_log_loads:
        raise SystemExit("_fb_log is still read in main.py")
    if len(logging_loads) != 1:
        raise SystemExit(f"logging has unexpected runtime reads: {len(logging_loads)}")

    assignment = fb_log_assignments[0]
    expected = 'logging.getLogger("broquer.facebook")'
    if ast.unparse(assignment.value) != expected:
        raise SystemExit(f"_fb_log assignment shape changed: {ast.unparse(assignment.value)!r}")

    spans = sorted(
        [
            (logging_import.lineno, logging_import.end_lineno),
            (assignment.lineno, assignment.end_lineno),
        ],
        reverse=True,
    )
    lines = source.splitlines(keepends=True)
    for start, end in spans:
        del lines[start - 1 : end]

    updated = "".join(lines)
    ast.parse(updated)
    MAIN.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
