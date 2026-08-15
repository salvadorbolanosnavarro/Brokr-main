#!/usr/bin/env python3
"""One-shot AST-bounded refactor of EasyBroker integration writes to Core DB."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "main.py"

NEW_SET = '''async def set_eb_key(req: EbKeyRequest, request: Request):
    # La cuenta de EasyBroker es de la EMPRESA. Solo el dueño o quien él designe.
    user_id = await exigir_gestion_integraciones(request)
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

    # Validar la key contra EasyBroker antes de guardar
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            test = await client.get(
                f"{EB_BASE}/properties?limit=1",
                headers={"X-Authorization": req.key.strip(), "accept": "application/json"}
            )
            print(f"[set_eb_key] EasyBroker validation status: {test.status_code}, body[:200]: {test.text[:200]}")
            if test.status_code == 401:
                raise HTTPException(status_code=400, detail="API key de EasyBroker invalida. Verifica que la copiaste correctamente.")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[set_eb_key] Excepcion en validacion: {type(e).__name__}: {e}")
        pass

    payload = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "provider": "easybroker",
        "api_key": req.key.strip(),
        "updated_at": datetime.utcnow().isoformat()
    }
    try:
        await post_rows(
            "user_integrations",
            payload,
            prefer="resolution=merge-duplicates,return=minimal",
            timeout=10,
        )
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        err_body = e.response.text or ""
        print(f"[set_eb_key] Supabase respondió {status}: {err_body}")
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo guardar la API key (Supabase {status}). Reintenta o avisa a soporte si persiste."
        )
    return {"ok": True, "saved": True, "scope": "user"}
'''

NEW_DELETE = '''async def delete_eb_key(request: Request):
    # Desconectar deja SIN INVENTARIO a todo el equipo. Solo el dueño o designado.
    user_id = await exigir_gestion_integraciones(request)
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado.")
    try:
        await delete_rows(
            "user_integrations",
            {
                "org_id": f"eq.{await get_org_id_for_user(user_id)}",
                "provider": "eq.easybroker",
            },
            timeout=10,
        )
    except httpx.HTTPStatusError:
        # Compatibilidad: históricamente los status HTTP de Supabase se ignoraban.
        pass
    return {"ok": True, "deleted": True}
'''


def _function_span(source: str, name: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"expected one top-level async function {name}, found {len(matches)}")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: node.lineno - 1])
    end = sum(len(line) for line in lines[: node.end_lineno])
    return start, end, source[start:end]


def _replace_function(source: str, name: str, replacement: str) -> str:
    start, end, _ = _function_span(source, name)
    return source[:start] + replacement + source[end:]


def transform(source: str) -> str:
    _, _, old_set = _function_span(source, "set_eb_key")
    _, _, old_delete = _function_span(source, "delete_eb_key")
    if old_set.count("/rest/v1/user_integrations") != 1:
        raise RuntimeError("set_eb_key no longer has exactly one expected direct REST write")
    if old_delete.count("/rest/v1/user_integrations") != 1:
        raise RuntimeError("delete_eb_key no longer has exactly one expected direct REST delete")

    updated = source
    updated = _replace_function(updated, "set_eb_key", NEW_SET)
    updated = _replace_function(updated, "delete_eb_key", NEW_DELETE)

    old_import = "from core.database import get_rows, post_rows"
    new_import = "from core.database import delete_rows, get_rows, post_rows"
    if old_import not in updated:
        raise RuntimeError("expected Core database import not found")
    updated = updated.replace(old_import, new_import, 1)

    if updated.count("/rest/v1/user_integrations") != source.count("/rest/v1/user_integrations") - 2:
        raise RuntimeError("user_integrations REST references did not decrease exactly twice")

    _, _, new_set = _function_span(updated, "set_eb_key")
    _, _, new_delete = _function_span(updated, "delete_eb_key")
    for marker in (
        'await post_rows(',
        'prefer="resolution=merge-duplicates,return=minimal"',
        'except httpx.HTTPStatusError as e:',
        'detail=f"No se pudo guardar la API key (Supabase {status}). Reintenta o avisa a soporte si persiste."',
    ):
        if marker not in new_set:
            raise RuntimeError(f"missing set_eb_key invariant: {marker}")
    for marker in (
        'await delete_rows(',
        '"provider": "eq.easybroker"',
        'except httpx.HTTPStatusError:',
        'return {"ok": True, "deleted": True}',
    ):
        if marker not in new_delete:
            raise RuntimeError(f"missing delete_eb_key invariant: {marker}")

    compile(updated, "main.py", "exec")
    return updated


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    updated = transform(source)
    if updated == source:
        raise RuntimeError("transform produced no change")
    TARGET.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
