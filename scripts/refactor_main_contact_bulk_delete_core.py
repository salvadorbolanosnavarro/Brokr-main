from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

old = '''                rd = await client.delete(\n                    f"{SUPABASE_URL}/rest/v1/contactos",\n                    headers={**sb_headers, "Prefer": "return=minimal"},\n                    params={**filtro, "id": f"in.({lista})"},\n                )\n                if rd.status_code in (200, 204):\n                    eliminados += len(lote)\n'''
new = '''                try:\n                    await delete_rows(\n                        "contactos",\n                        {**filtro, "id": f"in.({lista})"},\n                        prefer="return=minimal",\n                        timeout=60,\n                        accepted_statuses=(200, 204),\n                    )\n                    eliminados += len(lote)\n                except httpx.HTTPStatusError:\n                    pass\n'''

if source.count(old) == 1:
    source = source.replace(old, new, 1)
elif source.count(new) != 1:
    raise SystemExit(f"unexpected contact bulk delete state old={source.count(old)} new={source.count(new)}")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
