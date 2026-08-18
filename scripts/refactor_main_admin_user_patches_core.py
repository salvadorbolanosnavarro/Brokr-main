from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

replacements = [
(
'''    async with httpx.AsyncClient(timeout=10) as client:\n        r = await client.patch(\n            f"{SUPABASE_URL}/rest/v1/usuarios?id=eq.{target_id}",\n            headers={\n                "apikey": SUPABASE_SERVICE_KEY,\n                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                "Content-Type": "application/json",\n                "Prefer": "return=minimal",\n            },\n            json={"rol": req.rol},\n        )\n    if r.status_code not in (200, 204):\n        raise HTTPException(status_code=500, detail=f"Error actualizando rol: {r.text}")\n''',
'''    try:\n        await patch_rows_no_response(\n            "usuarios",\n            {"id": f"eq.{target_id}"},\n            {"rol": req.rol},\n            prefer="return=minimal",\n            timeout=10,\n            accepted_statuses=(200, 204),\n        )\n    except httpx.HTTPStatusError as exc:\n        raise HTTPException(status_code=500, detail=f"Error actualizando rol: {exc.response.text}")\n'''
),
(
'''    async with httpx.AsyncClient(timeout=10) as client:\n        r = await client.patch(\n            f"{SUPABASE_URL}/rest/v1/usuarios?id=eq.{target_id}",\n            headers={\n                "apikey": SUPABASE_SERVICE_KEY,\n                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                "Content-Type": "application/json",\n                "Prefer": "return=minimal",\n            },\n            json={"activo": bool(req.activo)},\n        )\n    if r.status_code not in (200, 204):\n        raise HTTPException(status_code=500, detail=f"Error actualizando activo: {r.text}")\n''',
'''    try:\n        await patch_rows_no_response(\n            "usuarios",\n            {"id": f"eq.{target_id}"},\n            {"activo": bool(req.activo)},\n            prefer="return=minimal",\n            timeout=10,\n            accepted_statuses=(200, 204),\n        )\n    except httpx.HTTPStatusError as exc:\n        raise HTTPException(status_code=500, detail=f"Error actualizando activo: {exc.response.text}")\n'''
),
]

for old, new in replacements:
    if source.count(old) == 1:
        source = source.replace(old, new, 1)
    elif source.count(new) != 1:
        raise SystemExit("unexpected admin patch state")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
