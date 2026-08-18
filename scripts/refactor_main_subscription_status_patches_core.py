from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

replacements = [
    (
'''            async with httpx.AsyncClient(timeout=8) as client:\n                await client.patch(\n                    f"{SUPABASE_URL}/rest/v1/suscripciones?stripe_subscription_id=eq.{subscription_id}",\n                    headers={\n                        "apikey": SUPABASE_SERVICE_KEY,\n                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                        "Content-Type": "application/json",\n                        "Prefer": "return=minimal",\n                    },\n                    json={"status": new_status, "updated_at": datetime.utcnow().isoformat()}\n                )\n''',
'''            try:\n                await patch_rows(\n                    "suscripciones",\n                    {"stripe_subscription_id": f"eq.{subscription_id}"},\n                    {"status": new_status, "updated_at": datetime.utcnow().isoformat()},\n                    prefer="return=minimal",\n                    timeout=8,\n                )\n            except httpx.HTTPStatusError:\n                # Historical webhook behavior: HTTP rejection did not abort processing.\n                pass\n'''
    ),
    (
'''            async with httpx.AsyncClient(timeout=8) as client:\n                await client.patch(\n                    f"{SUPABASE_URL}/rest/v1/suscripciones?stripe_subscription_id=eq.{subscription_id}",\n                    headers={\n                        "apikey": SUPABASE_SERVICE_KEY,\n                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                        "Content-Type": "application/json",\n                        "Prefer": "return=minimal",\n                    },\n                    json={"status": "past_due", "updated_at": datetime.utcnow().isoformat()}\n                )\n''',
'''            try:\n                await patch_rows(\n                    "suscripciones",\n                    {"stripe_subscription_id": f"eq.{subscription_id}"},\n                    {"status": "past_due", "updated_at": datetime.utcnow().isoformat()},\n                    prefer="return=minimal",\n                    timeout=8,\n                )\n            except httpx.HTTPStatusError:\n                # Historical webhook behavior: HTTP rejection did not abort processing.\n                pass\n'''
    ),
    (
'''    async with httpx.AsyncClient(timeout=10) as client:\n        await client.patch(\n            f"{SUPABASE_URL}/rest/v1/usuarios?id=eq.{user_id}",\n            headers={\n                "apikey": SUPABASE_SERVICE_KEY,\n                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                "Content-Type": "application/json",\n                "Prefer": "return=minimal",\n            },\n            json={"trial_max_usado": True},\n        )\n''',
'''    try:\n        await patch_rows(\n            "usuarios",\n            {"id": f"eq.{user_id}"},\n            {"trial_max_usado": True},\n            prefer="return=minimal",\n            timeout=10,\n        )\n    except httpx.HTTPStatusError:\n        # Historical trial-burn behavior: HTTP rejection did not abort success.\n        pass\n'''
    ),
    (
'''    async with httpx.AsyncClient(timeout=8) as client:\n        await client.patch(\n            f"{SUPABASE_URL}/rest/v1/suscripciones?user_id=eq.{user_id}",\n            headers={\n                "apikey": SUPABASE_SERVICE_KEY,\n                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                "Content-Type": "application/json",\n                "Prefer": "return=minimal",\n            },\n            json={"status": "canceled", "updated_at": datetime.utcnow().isoformat()}\n        )\n''',
'''    try:\n        await patch_rows(\n            "suscripciones",\n            {"user_id": f"eq.{user_id}"},\n            {"status": "canceled", "updated_at": datetime.utcnow().isoformat()},\n            prefer="return=minimal",\n            timeout=8,\n        )\n    except httpx.HTTPStatusError:\n        # Historical cancellation behavior: local Supabase HTTP rejection was ignored.\n        pass\n'''
    ),
]

for old, new in replacements:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one match, found {count}: {old.splitlines()[0]}")
    source = source.replace(old, new, 1)

path.write_text(source, encoding="utf-8")
