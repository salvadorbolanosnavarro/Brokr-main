#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_contact_write.py"
IMPORT_MODULE = "routers.whatsapp_contact_write"
SPECS = {
    "wa2_agregar_nota": (
        "wa2_agregar_nota_core",
        '''async def wa2_agregar_nota(contacto_id: str, req: NotaReq, request: Request):\n    return await wa2_agregar_nota_core(\n        contacto_id, req, request,\n        _require_user=_require_user, _ids_visibles=_ids_visibles, sb_get=sb_get,\n        _in_filter=_in_filter, HTTPException=HTTPException, _now=_now, sb_patch=sb_patch,\n        _sincronizar_contacto_crm=_sincronizar_contacto_crm,\n    )\n''',
        {"_require_user", "_ids_visibles", "sb_get", "_in_filter", "HTTPException", "_now", "sb_patch", "_sincronizar_contacto_crm"},
    ),
    "wa2_contacto_patch": (
        "wa2_contacto_patch_core",
        '''async def wa2_contacto_patch(contacto_id: str, request: Request):\n    return await wa2_contacto_patch_core(\n        contacto_id, request,\n        _require_user=_require_user, _ids_visibles=_ids_visibles, _in_filter=_in_filter,\n        _now=_now, sb_patch=sb_patch,\n    )\n''',
        {"_require_user", "_ids_visibles", "_in_filter", "_now", "sb_patch"},
    ),
}


def fn(tree, name):
    xs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(xs) != 1:
        raise SystemExit(f"expected one {name}, found {len(xs)}")
    return xs[0]


def shape(node):
    m = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(m)
    return ast.dump(m, annotate_fields=True, include_attributes=False)


def main():
    text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    canon = ast.parse(CANONICAL.read_text(encoding="utf-8"))

    replacements = []
    for legacy_name, (core_name, wrapper_text, _) in SPECS.items():
        legacy = fn(tree, legacy_name)
        core = fn(canon, core_name)
        if shape(legacy) != shape(core):
            raise SystemExit(f"contact write body differs: {legacy_name}")
        replacements.append((legacy.lineno, legacy.end_lineno, wrapper_text))

    lines = text.splitlines(keepends=True)
    for start, end, wrapper_text in sorted(replacements, reverse=True):
        lines[start - 1:end] = [wrapper_text, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("contact write already imported")

    # Insert before the first route decorator, never between decorator and def.
    first_node = min((fn(t2, name) for name in SPECS), key=lambda n: n.lineno)
    insert_line = min([d.lineno for d in first_node.decorator_list] or [first_node.lineno])
    cur = mid.splitlines(keepends=True)
    import_text = (
        "from routers.whatsapp_contact_write import (\n"
        "    wa2_agregar_nota_core, wa2_contacto_patch_core,\n"
        ")\n\n"
    )
    cur[insert_line - 1:insert_line - 1] = [import_text]
    out = "".join(cur)
    t3 = ast.parse(out)

    for legacy_name, (core_name, _, expected) in SPECS.items():
        wrapper = fn(t3, legacy_name)
        calls = [n for n in ast.walk(wrapper) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == core_name]
        if len(calls) != 1 or {k.arg for k in calls[0].keywords} != expected:
            raise SystemExit(f"contact write wrapper contract differs: {legacy_name}")
        if not wrapper.decorator_list:
            raise SystemExit(f"route decorator lost: {legacy_name}")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
