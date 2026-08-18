from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

old_import = "from core.database import call_public_rpc, delete_rows, get_public_rows, get_rows, get_service_json, patch_rows, patch_rows_no_response, post_rows, upsert_rows"
new_import = "from core.database import call_public_rpc, call_service_rpc, delete_rows, get_public_rows, get_rows, get_service_json, patch_rows, patch_rows_no_response, post_rows, upsert_rows"
if source.count(old_import) == 1:
    source = source.replace(old_import, new_import, 1)
elif source.count(new_import) != 1:
    raise SystemExit("unexpected core.database import state")

old_get = '''    # Verificar que el objetivo existe y validar correo + rol\n    async with httpx.AsyncClient(timeout=10) as client:\n        r = await client.get(\n            f"{SUPABASE_URL}/rest/v1/usuarios",\n            headers={\n                "apikey": SUPABASE_SERVICE_KEY,\n                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n            },\n            params={"id": f"eq.{target_id}", "select": "id,email,rol", "limit": "1"},\n        )\n    filas = r.json() if r.status_code == 200 else []\n'''
new_get = '''    # Verificar que el objetivo existe y validar correo + rol\n    try:\n        filas = await get_service_json(\n            "usuarios",\n            {"id": f"eq.{target_id}", "select": "id,email,rol", "limit": "1"},\n            timeout=10,\n            accepted_statuses=(200,),\n        )\n    except httpx.HTTPStatusError:\n        filas = []\n'''

old_rpc = '''    # Ejecutar la eliminación total vía RPC (service key)\n    async with httpx.AsyncClient(timeout=60) as client:\n        r = await client.post(\n            f"{SUPABASE_URL}/rest/v1/rpc/admin_eliminar_usuario_total",\n            headers={\n                "apikey": SUPABASE_SERVICE_KEY,\n                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                "Content-Type": "application/json",\n            },\n            json={"p_user_id": target_id},\n        )\n    if r.status_code != 200:\n        raise HTTPException(status_code=500, detail=f"Error eliminando usuario: {r.text}")\n    resultado = r.json()\n'''
new_rpc = '''    # Ejecutar la eliminación total vía RPC (service key)\n    try:\n        resultado = await call_service_rpc(\n            "admin_eliminar_usuario_total",\n            {"p_user_id": target_id},\n            timeout=60,\n            accepted_statuses=(200,),\n        )\n    except httpx.HTTPStatusError as exc:\n        raise HTTPException(status_code=500, detail=f"Error eliminando usuario: {exc.response.text}")\n'''

for old, new, label in [(old_get, new_get, "admin get"), (old_rpc, new_rpc, "admin rpc")]:
    if source.count(old) == 1:
        source = source.replace(old, new, 1)
    elif source.count(new) != 1:
        raise SystemExit(f"unexpected {label} state")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
