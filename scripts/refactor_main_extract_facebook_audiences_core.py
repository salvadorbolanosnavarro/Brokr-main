"""Deterministically extract Facebook custom/lookalike audiences from main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
FUNCTIONS = {
    "_hash_meta",
    "_normaliza_email",
    "_normaliza_telefono",
    "facebook_audience_from_contacts",
    "facebook_audience_lookalike",
    "_fb_guardar_audiencia",
}
CLASSES = {"FbAudienceRequest", "FbLookalikeRequest"}
IMPORT = "from routers.facebook_audiences import router as facebook_audiences_router\n"
MOUNT = "app.include_router(facebook_audiences_router)\n"


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    if IMPORT.strip() in source or MOUNT.strip() in source:
        raise SystemExit("Facebook audiences router already connected")

    tree = ast.parse(source)
    nodes: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FUNCTIONS:
            nodes[node.name] = node
        elif isinstance(node, ast.ClassDef) and node.name in CLASSES:
            nodes[node.name] = node
    expected = FUNCTIONS | CLASSES
    if set(nodes) != expected:
        raise SystemExit(f"expected audience nodes {sorted(expected)}, found {sorted(nodes)}")

    contracts = {
        "_hash_meta": ('hashlib.sha256', '.lower().encode("utf-8")'),
        "_normaliza_email": ('email.count("@") != 1', 'dominio.rsplit(".", 1)'),
        "_normaliza_telefono": ('re.sub(r"\\D", "", tel or "")', 'lada_pais + digitos[3:]'),
        "facebook_audience_from_contacts": (
            'exigir_gestion_integraciones(request)',
            '_get_fb_meta(user_id)',
            '"limit": "5000"',
            '"customer_file_source": "USER_PROVIDED_ONLY"',
            '"2654" in texto',
            'range(0, len(datos), 5000)',
            '"schema": ["EMAIL", "PHONE"]',
            'timeout=90',
            '"DELETE"',
            'reintentos=2',
            'if subidos < 100',
        ),
        "facebook_audience_lookalike": (
            '0.01 <= req.ratio <= 0.20',
            '"subtype": "LOOKALIKE"',
            '"type": "similarity"',
            '_fb_exigir_ok(r, "Error creando el público similar")',
        ),
        "_fb_guardar_audiencia": (
            '"fb_audiences"',
            'prefer="resolution=merge-duplicates,return=minimal"',
            'accepted_statuses=(200, 201, 204)',
            '_fb_avisa_migracion("guardar público", e.response)',
        ),
    }
    for name, required in contracts.items():
        block = ast.get_source_segment(source, nodes[name]) or ""
        missing = [fragment for fragment in required if fragment not in block]
        if missing:
            raise SystemExit(f"{name} source contract changed: {missing}")

    lines = source.splitlines(keepends=True)
    ranges = []
    for node in nodes.values():
        start = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))]) - 1
        ranges.append((start, node.end_lineno))
    for start, end in sorted(ranges, reverse=True):
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
        raise SystemExit(f"expected one app = FastAPI(), found {len(app_nodes)}")
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_nodes[0].lineno - 1, "\n" + IMPORT)
    transformed = "".join(lines)

    tree3 = ast.parse(transformed)
    app_nodes = [
        node for node in tree3.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_nodes[0].end_lineno, MOUNT + "\n")
    transformed = "".join(lines)

    check = ast.parse(transformed)
    remaining = set()
    for node in check.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in expected:
            remaining.add(node.name)
    if remaining:
        raise SystemExit(f"audience nodes remain in main.py: {sorted(remaining)}")
    if transformed.count(IMPORT.strip()) != 1 or transformed.count(MOUNT.strip()) != 1:
        raise SystemExit("unexpected audience import/mount count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted Facebook audiences")


if __name__ == "__main__":
    main()
