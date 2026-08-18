from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

old_import = "from core.database import call_public_rpc, delete_rows, get_public_rows, get_rows, patch_rows, post_rows, upsert_rows"
new_import = "from core.database import call_public_rpc, delete_rows, get_public_rows, get_rows, get_service_json, patch_rows, patch_rows_no_response, post_rows, upsert_rows"
if source.count(old_import) == 1:
    source = source.replace(old_import, new_import, 1)
elif source.count(new_import) != 1:
    raise SystemExit("unexpected core.database import state")

old_get = '''async def _sb_service_get(tabla: str, params: dict) -> list:\n    """GET a Supabase con service key. Devuelve [] si algo falla."""\n    async with httpx.AsyncClient(timeout=10) as client:\n        r = await client.get(\n            f"{SUPABASE_URL}/rest/v1/{tabla}",\n            headers={"apikey": SUPABASE_SERVICE_KEY,\n                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},\n            params=params,\n        )\n    if r.status_code != 200:\n        return []\n    try:\n        return r.json()\n    except Exception:\n        return []\n'''
new_get = '''async def _sb_service_get(tabla: str, params: dict) -> list:\n    """GET service-role legacy: HTTP != 200 / JSON inválido => []; transporte propaga."""\n    try:\n        return await get_service_json(\n            tabla,\n            params,\n            timeout=10,\n            accepted_statuses=(200,),\n        )\n    except httpx.HTTPStatusError:\n        return []\n    except json.JSONDecodeError:\n        return []\n'''

old_patch = '''async def _sb_service_patch(tabla: str, params: dict, payload: dict) -> None:\n    """PATCH a Supabase con service key."""\n    async with httpx.AsyncClient(timeout=10) as client:\n        await client.patch(\n            f"{SUPABASE_URL}/rest/v1/{tabla}",\n            headers={"apikey": SUPABASE_SERVICE_KEY,\n                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                     "Content-Type": "application/json",\n                     "Prefer": "return=minimal"},\n            params=params, json=payload,\n        )\n'''
new_patch = '''async def _sb_service_patch(tabla: str, params: dict, payload: dict) -> None:\n    """PATCH service-role legacy: cualquier status HTTP se ignora; transporte propaga."""\n    try:\n        await patch_rows_no_response(\n            tabla,\n            params,\n            payload,\n            prefer="return=minimal",\n            timeout=10,\n        )\n    except httpx.HTTPStatusError:\n        pass\n'''

for old, new, label in [(old_get, new_get, "get"), (old_patch, new_patch, "patch")]:
    if source.count(old) == 1:
        source = source.replace(old, new, 1)
    elif source.count(new) != 1:
        raise SystemExit(f"unexpected _sb_service_{label} state")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
