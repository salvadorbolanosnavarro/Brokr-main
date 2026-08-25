"""Deterministically move Facebook Ads creation persistence helpers out of main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
NAMES = {
    "_fb_reservar_creacion",
    "_fb_buscar_por_idempotencia",
    "_fb_actualizar_entidad",
}
IMPORT = (
    "from core.facebook_persistence import (\n"
    "    find_facebook_creation_by_idempotency as _fb_buscar_por_idempotencia,\n"
    "    reserve_facebook_creation as _fb_reservar_creacion,\n"
    "    update_facebook_entity as _fb_actualizar_entidad,\n"
    ")\n"
)


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    if IMPORT.strip() in source:
        raise SystemExit("Facebook Ads persistence Core import already present")
    tree = ast.parse(source)
    matches = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in NAMES
    }
    if set(matches) != NAMES:
        raise SystemExit(f"expected persistence helpers {sorted(NAMES)}, found {sorted(matches)}")

    contracts = {
        "_fb_reservar_creacion": (
            '"status": "CREANDO"',
            'prefer="return=representation"',
            'accepted_statuses=(200, 201)',
            'r.status_code == 409 and idempotency_key',
            '_fb_buscar_por_idempotencia(user_id, idempotency_key)',
            'return {"modo": "sin_tabla"}',
        ),
        "_fb_buscar_por_idempotencia": (
            '"idempotency_key": f"eq.{idempotency_key}"',
            '"limit": "1"',
            '_fb_avisa_migracion("buscar idempotencia", e.response)',
            'return {}',
        ),
        "_fb_actualizar_entidad": (
            '"updated_at": datetime.now(timezone.utc).isoformat()',
            '_fb_avisa_migracion("actualizar entidad", e.response)',
            'timeout=10',
        ),
    }
    for name, required in contracts.items():
        block = ast.get_source_segment(source, matches[name]) or ""
        missing = [fragment for fragment in required if fragment not in block]
        if missing:
            raise SystemExit(f"{name} source contract changed: {missing}")

    lines = source.splitlines(keepends=True)
    ranges = sorted(
        ((node.lineno - 1, node.end_lineno) for node in matches.values()),
        reverse=True,
    )
    for start, end in ranges:
        del lines[start:end]
    transformed = "".join(lines)

    tree2 = ast.parse(transformed)
    app_nodes = [
        node for node in tree2.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    if len(app_nodes) != 1:
        raise SystemExit(f"expected exactly one app = FastAPI(), found {len(app_nodes)}")
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_nodes[0].lineno - 1, "\n" + IMPORT)
    transformed = "".join(lines)

    check = ast.parse(transformed)
    remaining = {
        node.name for node in check.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in NAMES
    }
    if remaining:
        raise SystemExit(f"persistence helpers remain in main.py: {sorted(remaining)}")
    if transformed.count(IMPORT.strip()) != 1:
        raise SystemExit("unexpected Facebook Ads persistence Core import count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted Facebook Ads persistence helpers")


if __name__ == "__main__":
    main()
