"""Deterministically move Facebook Lead Ads processing helpers out of main.py."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
IMPORT_BLOCK = (
    "from core.facebook_leadgen_processor import (\n"
    "    FACEBOOK_LEAD_FIELDS as _FB_CAMPOS_LEAD,\n"
    "    find_facebook_page_owner as _fb_buscar_dueno_de_pagina,\n"
    "    process_facebook_lead as _fb_procesar_lead,\n"
    ")\n"
)
FUNCTIONS = {"_fb_buscar_dueno_de_pagina", "_fb_procesar_lead"}
ASSIGNMENT = "_FB_CAMPOS_LEAD"


def assignment_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)

    function_nodes: dict[str, ast.AsyncFunctionDef] = {}
    for name in FUNCTIONS:
        nodes = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name]
        if len(nodes) != 1:
            raise SystemExit(f"expected exactly one {name} async definition, found {len(nodes)}")
        function_nodes[name] = nodes[0]

    assignments = [n for n in tree.body if assignment_name(n) == ASSIGNMENT]
    if len(assignments) != 1:
        raise SystemExit(f"expected exactly one {ASSIGNMENT} assignment, found {len(assignments)}")
    assignment = assignments[0]

    owner_source = ast.get_source_segment(source, function_nodes["_fb_buscar_dueno_de_pagina"]) or ""
    processor_source = ast.get_source_segment(source, function_nodes["_fb_procesar_lead"]) or ""
    fields_source = ast.get_source_segment(source, assignment) or ""

    owner_fragments = (
        "if not page_id or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:",
        '"meta": f"like.*{page_id}*"',
        '"limit": "20"',
        '"limit": "500"',
        'descifrar_secreto(fila.get("api_key", ""))',
    )
    processor_fragments = (
        'leadgen_id = str(valor.get("leadgen_id") or "")',
        '"fb_leads_recibidos"',
        '_fb_avisa_migracion("procesar lead", e.response)',
        'async with httpx.AsyncClient(timeout=20) as client:',
        '"No se pudo leer el lead"',
        '"fuente": "Facebook Lead Ads"',
        '"etiquetas": ["Facebook", "Lead Ad"]',
        '"Contacto ya existía; se marcó como potencial."',
    )
    fields_fragments = (
        '"full_name": "nombre"',
        '"phone_number": "telefono"',
        '"post_code": "cp"',
    )
    for fragment in owner_fragments:
        if fragment not in owner_source:
            raise SystemExit(f"page-owner behavior changed: {fragment}")
    for fragment in processor_fragments:
        if fragment not in processor_source:
            raise SystemExit(f"Lead Ads processor behavior changed: {fragment}")
    for fragment in fields_fragments:
        if fragment not in fields_source:
            raise SystemExit(f"Lead Ads field map changed: {fragment}")

    required_webhook = (
        '@app.post("/facebook/leadgen/webhook")',
        "if not _FB_WEBHOOK_SECRET:",
        "hmac.compare_digest(firma, esperada)",
        "background.add_task(_fb_procesar_lead, valor)",
        "return Response(status_code=200)",
    )
    for fragment in required_webhook:
        if fragment not in source:
            raise SystemExit(f"Lead Ads webhook boundary changed: {fragment}")
    if "from core.facebook_leadgen_processor import" in source:
        raise SystemExit("Lead Ads processor Core already imported")

    lines = source.splitlines(keepends=True)
    nodes_to_remove: list[ast.AST] = [assignment, *function_nodes.values()]
    spans = [(node.lineno - 1, node.end_lineno) for node in nodes_to_remove if node.end_lineno is not None]
    if len(spans) != 3:
        raise SystemExit("could not resolve all Lead Ads processor spans")
    for start, end in sorted(spans, reverse=True):
        del lines[start:end]
    transformed = "".join(lines)

    tree2 = ast.parse(transformed)
    app_assignments = [
        n for n in tree2.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "FastAPI"
    ]
    if len(app_assignments) != 1:
        raise SystemExit(f"expected exactly one app = FastAPI(), found {len(app_assignments)}")
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_assignments[0].lineno - 1, "\n" + IMPORT_BLOCK)
    transformed = "".join(lines)

    check = ast.parse(transformed)
    leftover_functions = [n.name for n in check.body if isinstance(n, ast.AsyncFunctionDef) and n.name in FUNCTIONS]
    leftover_assignments = [assignment_name(n) for n in check.body if assignment_name(n) == ASSIGNMENT]
    if leftover_functions or leftover_assignments:
        raise SystemExit(
            f"Lead Ads processor legacy definitions remain: {leftover_functions + leftover_assignments}"
        )
    if transformed.count("from core.facebook_leadgen_processor import (") != 1:
        raise SystemExit("unexpected Lead Ads processor Core import count")
    for fragment in required_webhook:
        if fragment not in transformed:
            raise SystemExit(f"Lead Ads webhook boundary lost: {fragment}")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted Facebook Lead Ads processor core")


if __name__ == "__main__":
    main()
