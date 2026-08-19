#!/usr/bin/env python3
"""Move shared Stripe subscription configuration from main.py to core.stripe."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

IMPORT = '''from core.stripe import (
    EMPRESA_ASIENTOS_BASE, EMPRESA_ASIENTOS_MAX, EMPRESA_TARIFAS,
    PROMO_CODE_AMPI, STRIPE_PRICE_AMPI, STRIPE_PRICE_PRO,
    STRIPE_PRICE_EMPRESA_ANUAL, STRIPE_PRICE_EMPRESA_EXTRA_ANUAL,
    STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL, STRIPE_PRICE_EMPRESA_MENSUAL,
    STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, TRIAL_MAX_DIAS,
    precio_empresa as _precio_empresa, stripe_headers as _stripe_headers,
)
'''

ASSIGNMENTS = {
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_PRO",
    "STRIPE_PRICE_AMPI",
    "STRIPE_PRICE_EMPRESA_MENSUAL",
    "STRIPE_PRICE_EMPRESA_ANUAL",
    "STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL",
    "STRIPE_PRICE_EMPRESA_EXTRA_ANUAL",
    "EMPRESA_ASIENTOS_BASE",
    "EMPRESA_ASIENTOS_MAX",
    "EMPRESA_TARIFAS",
    "PROMO_CODE_AMPI",
    "TRIAL_MAX_DIAS",
}
FUNCTIONS = {"_precio_empresa", "_stripe_headers"}


def _assigned_names(node: ast.AST) -> set[str]:
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return set()
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names = set()
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
    return names


def transform_source(source: str) -> str:
    tree = ast.parse(source)
    ranges: list[tuple[int, int]] = []
    seen_assignments: set[str] = set()
    seen_functions: set[str] = set()

    for node in tree.body:
        names = _assigned_names(node) & ASSIGNMENTS
        if names:
            seen_assignments |= names
            ranges.append((node.lineno, node.end_lineno or node.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FUNCTIONS:
            seen_functions.add(node.name)
            ranges.append((node.lineno, node.end_lineno or node.lineno))

    missing_assignments = ASSIGNMENTS - seen_assignments
    missing_functions = FUNCTIONS - seen_functions
    if missing_assignments or missing_functions:
        # Idempotent state: all symbols already imported from Core.
        if IMPORT in source and not (seen_assignments or seen_functions):
            compile(source, str(MAIN), "exec")
            return source
        raise RuntimeError(
            f"Unexpected Stripe config state: missing assignments={sorted(missing_assignments)}, "
            f"missing functions={sorted(missing_functions)}"
        )

    lines = source.splitlines(keepends=True)
    for start, end in sorted(ranges, reverse=True):
        del lines[start - 1:end]
    transformed = "".join(lines)

    anchor = "from core.subscriptions import "
    idx = transformed.find(anchor)
    if idx < 0:
        raise RuntimeError("core.subscriptions import anchor not found")
    line_end = transformed.find("\n", idx)
    # Handle the existing parenthesized multi-line import.
    if transformed[idx:line_end].rstrip().endswith("("):
        close = transformed.find("\n)", line_end)
        if close < 0:
            raise RuntimeError("unterminated core.subscriptions import")
        line_end = close + 2
    else:
        line_end += 1
    if IMPORT not in transformed:
        transformed = transformed[:line_end] + IMPORT + transformed[line_end:]

    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
