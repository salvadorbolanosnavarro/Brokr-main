from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

repls = [
(
'''                rs = await client.get(\n                    f"{SUPABASE_URL}/rest/v1/suscripciones",\n                    headers=sb_read_headers,\n                    params={\n                        "user_id": f"eq.{user_id}",\n                        "select": "stripe_subscription_id",\n                        "order": "updated_at.desc",\n                        "limit": "1",\n                    },\n                )\n                sub_rows = rs.json() if rs.status_code == 200 else []\n''',
'''                try:\n                    sub_rows = await get_service_json(\n                        "suscripciones",\n                        {\n                            "user_id": f"eq.{user_id}",\n                            "select": "stripe_subscription_id",\n                            "order": "updated_at.desc",\n                            "limit": "1",\n                        },\n                        timeout=30,\n                        accepted_statuses=(200,),\n                    )\n                except httpx.HTTPStatusError:\n                    sub_rows = []\n'''
),
(
'''            rp = await client.get(\n                f"{SUPABASE_URL}/rest/v1/propiedades",\n                headers=sb_read_headers,\n                params={"user_id": f"eq.{user_id}", "select": "fotos"},\n            )\n            objetos = []\n            if rp.status_code == 200:\n                for fila in (rp.json() or []):\n                    for url in (fila.get("fotos") or []):\n                        if not isinstance(url, str):\n                            continue\n                        marcador = "/fotos-propiedades/"\n                        if marcador in url:\n                            nombre = url.split(marcador, 1)[1].split("?", 1)[0]\n                            if nombre:\n                                objetos.append(nombre)\n''',
'''            try:\n                filas_fotos = await get_service_json(\n                    "propiedades",\n                    {"user_id": f"eq.{user_id}", "select": "fotos"},\n                    timeout=30,\n                    accepted_statuses=(200,),\n                )\n            except httpx.HTTPStatusError:\n                filas_fotos = []\n            objetos = []\n            for fila in (filas_fotos or []):\n                for url in (fila.get("fotos") or []):\n                    if not isinstance(url, str):\n                        continue\n                    marcador = "/fotos-propiedades/"\n                    if marcador in url:\n                        nombre = url.split(marcador, 1)[1].split("?", 1)[0]\n                        if nombre:\n                            objetos.append(nombre)\n'''
),
(
'''        for tabla in tablas:\n            try:\n                r = await client.delete(\n                    f"{SUPABASE_URL}/rest/v1/{tabla}?user_id=eq.{user_id}",\n                    headers=sb_headers,\n                )\n                borrados[tabla] = (r.status_code in (200, 204))\n                if r.status_code not in (200, 204):\n                    errores.append(f"{tabla}: {r.status_code} {r.text[:120]}")\n            except Exception as e:\n                errores.append(f"{tabla}: {e}")\n                borrados[tabla] = False\n''',
'''        for tabla in tablas:\n            try:\n                await delete_rows(\n                    tabla,\n                    {"user_id": f"eq.{user_id}"},\n                    timeout=30,\n                    accepted_statuses=(200, 204),\n                )\n                borrados[tabla] = True\n            except httpx.HTTPStatusError as e:\n                errores.append(f"{tabla}: {e.response.status_code} {e.response.text[:120]}")\n                borrados[tabla] = False\n            except Exception as e:\n                errores.append(f"{tabla}: {e}")\n                borrados[tabla] = False\n'''
),
(
'''        # Borrar fila en `usuarios` (el id es el mismo de auth.users)\n        try:\n            r = await client.delete(\n                f"{SUPABASE_URL}/rest/v1/usuarios?id=eq.{user_id}",\n                headers=sb_headers,\n            )\n            borrados["usuarios"] = (r.status_code in (200, 204))\n        except Exception as e:\n            errores.append(f"usuarios: {e}")\n            borrados["usuarios"] = False\n''',
'''        # Borrar fila en `usuarios` (el id es el mismo de auth.users)\n        try:\n            await delete_rows(\n                "usuarios",\n                {"id": f"eq.{user_id}"},\n                timeout=30,\n                accepted_statuses=(200, 204),\n            )\n            borrados["usuarios"] = True\n        except httpx.HTTPStatusError:\n            # Historical behavior: HTTP rejection only marked this row as not deleted.\n            borrados["usuarios"] = False\n        except Exception as e:\n            errores.append(f"usuarios: {e}")\n            borrados["usuarios"] = False\n'''
),
]

for old, new in repls:
    if source.count(old) == 1:
        source = source.replace(old, new, 1)
    elif source.count(new) != 1:
        raise SystemExit(f"unexpected self-delete transform state: {old.splitlines()[0]}")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
