"""One-time deterministic migration of Facebook connection persistence in main.py.

Moves only the user_integrations persistence used by save/read/patch/disconnect to
core.database. Meta Graph API behavior, encryption and authorization are untouched.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "main.py"
RAW_INTEGRATIONS = "/rest/v1/user_integrations"


def _splice(source: str, start: str, end: str, replacement: str) -> str:
    if source.count(start) != 1:
        raise AssertionError(f"expected one start marker: {start!r}")
    start_i = source.index(start)
    end_i = source.index(end, start_i)
    return source[:start_i] + replacement.rstrip() + "\n\n\n" + source[end_i:]


def transform_source(source: str) -> str:
    before_raw = source.count(RAW_INTEGRATIONS)

    old_save = '''    async with httpx.AsyncClient(timeout=10) as client:\n        await client.post(\n            f"{SUPABASE_URL}/rest/v1/user_integrations",\n            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                     "Content-Type": "application/json",\n                     "Prefer": "resolution=merge-duplicates,return=minimal"},\n            json=payload\n        )'''
    new_save = '''    try:\n        await post_rows(\n            "user_integrations",\n            payload,\n            prefer="resolution=merge-duplicates,return=minimal",\n            timeout=10,\n        )\n    except httpx.HTTPStatusError:\n        # Historical behavior: Supabase HTTP rejections did not fail save-page.\n        pass'''
    if source.count(old_save) != 1:
        raise AssertionError("facebook save-page persistence block changed")
    source = source.replace(old_save, new_save, 1)

    connection = '''@app.get("/facebook/connection")
async def facebook_get_connection(request: Request):
    """Devuelve si el usuario tiene Facebook conectado y el nombre de la página."""
    user_id = await get_user_id_from_token(request)
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return {"connected": False}
    try:
        rows = await get_rows(
            "user_integrations",
            {
                "user_id": f"eq.{user_id}",
                "provider": "eq.facebook",
                "select": "api_key,meta",
                "limit": "1",
            },
            timeout=8,
        )
        if rows and rows[0].get("api_key"):
            meta_str = rows[0].get("meta", "{}")
            try:
                meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
            except Exception:
                meta = {}
            estado_token = _fb_estado_token(meta)
            return {
                "connected": True,
                "page_id": meta.get("page_id", ""),
                "page_name": meta.get("page_name", "Página conectada"),
                "page_pic": meta.get("page_pic", ""),
                # Los tokens YA NO viajan al navegador. El frontend solo
                # los usaba para saber si existían; mandarlos era regalar
                # permiso de gastar a cualquier extensión o XSS que
                # leyera la respuesta. El backend los saca de Supabase
                # cuando los necesita.
                "tiene_token_ads": bool(meta.get("user_token")),
                "ad_account_id": meta.get("ad_account_id", ""),
                "ad_account_name": meta.get("ad_account_name", ""),
                # Estado del token: la UI avisa ANTES de que expire, en
                # vez de que el agente descubra el corte cuando ya no
                # puede pausar una campaña que está gastando.
                "token": estado_token,
                "scopes_faltantes": [s for s in _FB_SCOPES_REQUERIDOS
                                     if s not in (meta.get("scopes") or [])]
                                    if meta.get("scopes") else [],
            }
    except Exception:
        pass
    return {"connected": False}'''
    source = _splice(
        source,
        '@app.get("/facebook/connection")',
        'async def _fb_get_meta_row',
        connection,
    )

    get_row = '''async def _fb_get_meta_row(user_id: str) -> dict:
    """Devuelve la fila completa (api_key + meta dict) del usuario, o {}."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {}
    try:
        rows = await get_rows(
            "user_integrations",
            {
                "user_id": f"eq.{user_id}",
                "provider": "eq.facebook",
                "select": "api_key,meta",
                "limit": "1",
            },
            timeout=10,
        )
    except httpx.HTTPStatusError:
        # Historical behavior: an HTTP rejection meant "no row"; transport
        # failures still propagate to callers.
        return {}
    if not rows:
        return {}
    row = rows[0]
    meta_raw = row.get("meta", "{}")
    try:
        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    except Exception:
        meta = {}
    # Los tokens salen ya descifrados: quien llame a este helper no tiene por
    # qué saber si están cifrados en reposo o no.
    if meta.get("user_token"):
        meta["user_token"] = descifrar_secreto(meta["user_token"])
    return {"page_token": descifrar_secreto(row.get("api_key", "")), "meta": meta}'''
    source = _splice(source, 'async def _fb_get_meta_row', 'async def _fb_patch_meta', get_row)

    patch_meta = '''async def _fb_patch_meta(user_id: str, updates: dict, new_page_token: str | None = None) -> None:
    """Actualiza la fila de Facebook del usuario fusionando 'updates' en meta.

    Al reescribir, los tokens quedan cifrados aunque hubieran entrado en claro:
    así las conexiones viejas se van migrando solas con el uso normal.
    """
    cur = await _fb_get_meta_row(user_id)
    meta = cur.get("meta") or {}
    meta.update(updates)
    if meta.get("user_token"):
        meta["user_token"] = cifrar_secreto(meta["user_token"])
    page_token = new_page_token if new_page_token is not None else cur.get("page_token", "")
    payload = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "provider": "facebook",
        "api_key": cifrar_secreto(page_token),
        "meta": json.dumps(meta),
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await post_rows(
            "user_integrations",
            payload,
            prefer="resolution=merge-duplicates,return=minimal",
            timeout=10,
        )
    except httpx.HTTPStatusError:
        # Historical behavior: HTTP rejection was ignored; transport failures
        # still propagate.
        pass'''
    source = _splice(source, 'async def _fb_patch_meta', '@app.get("/facebook/pages")', patch_meta)

    disconnect = '''@app.delete("/facebook/connection")
async def facebook_disconnect(request: Request):
    """Elimina la conexión de Facebook de la EMPRESA en Supabase.
    Deja al equipo entero sin anuncios: solo el dueño o quien él designe."""
    user_id = await exigir_gestion_integraciones(request)
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no configurado")
    try:
        await delete_rows(
            "user_integrations",
            {"user_id": f"eq.{user_id}", "provider": "eq.facebook"},
            timeout=10,
        )
    except httpx.HTTPStatusError:
        # Historical behavior: HTTP rejection was ignored; transport failures
        # still propagate.
        pass
    return {"ok": True}'''
    source = _splice(
        source,
        '@app.delete("/facebook/connection")',
        '@app.post("/facebook/publish-property")',
        disconnect,
    )

    after_raw = source.count(RAW_INTEGRATIONS)
    if before_raw - after_raw != 5:
        raise AssertionError(
            f"expected exactly 5 Facebook connection REST removals, got {before_raw - after_raw}"
        )
    compile(source, "main.py", "exec")
    return source


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    transformed = transform_source(original)
    if transformed == original:
        raise AssertionError("transform produced no changes")
    TARGET.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
