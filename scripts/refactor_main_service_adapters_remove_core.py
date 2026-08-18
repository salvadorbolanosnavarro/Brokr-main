from pathlib import Path

core_path = Path("core/database.py")
main_path = Path("main.py")
core = core_path.read_text(encoding="utf-8")
main = main_path.read_text(encoding="utf-8")

# Core: explicit legacy-compatible policies, with transport failures still propagating.
if "import json\n" not in core:
    core = core.replace("from typing import Any, Mapping, Optional\n\nimport httpx\n", "from typing import Any, Mapping, Optional\n\nimport json\nimport httpx\n", 1)

anchor = "async def call_public_rpc(\n"
helpers = '''async def get_service_json_or_empty(\n    table: str,\n    params: Mapping[str, Any],\n    *,\n    timeout: httpx.Timeout | float = 10,\n) -> Any:\n    """Legacy-compatible service GET: HTTP rejection/invalid JSON => []; transport propagates."""\n    try:\n        return await get_service_json(\n            table,\n            params,\n            timeout=timeout,\n            accepted_statuses=(200,),\n        )\n    except httpx.HTTPStatusError:\n        return []\n    except json.JSONDecodeError:\n        return []\n\n\nasync def patch_rows_ignoring_http_status(\n    table: str,\n    params: Mapping[str, Any],\n    payload: Mapping[str, Any],\n    *,\n    timeout: httpx.Timeout | float = 10,\n) -> None:\n    """Legacy-compatible service PATCH: ignore HTTP status rejection, propagate transport."""\n    try:\n        await patch_rows_no_response(\n            table,\n            params,\n            payload,\n            prefer="return=minimal",\n            timeout=timeout,\n        )\n    except httpx.HTTPStatusError:\n        pass\n\n\n'''
if "async def get_service_json_or_empty(" not in core:
    if core.count(anchor) != 1:
        raise SystemExit("unexpected Core RPC anchor")
    core = core.replace(anchor, helpers + anchor, 1)

# main.py: remove local compatibility adapters and use the named Core policies directly.
old_defs = '''async def _sb_service_get(tabla: str, params: dict) -> list:\n    """GET service-role legacy: HTTP != 200 / JSON inválido => []; transporte propaga."""\n    try:\n        return await get_service_json(\n            tabla,\n            params,\n            timeout=10,\n            accepted_statuses=(200,),\n        )\n    except httpx.HTTPStatusError:\n        return []\n    except json.JSONDecodeError:\n        return []\n\n\nasync def _sb_service_patch(tabla: str, params: dict, payload: dict) -> None:\n    """PATCH service-role legacy: cualquier status HTTP se ignora; transporte propaga."""\n    try:\n        await patch_rows_no_response(\n            tabla,\n            params,\n            payload,\n            prefer="return=minimal",\n            timeout=10,\n        )\n    except httpx.HTTPStatusError:\n        pass\n\n\n'''
if old_defs in main:
    main = main.replace(old_defs, "", 1)
elif "async def _sb_service_get(" in main or "async def _sb_service_patch(" in main:
    raise SystemExit("unexpected local service adapter definitions")

old_import = "from core.database import call_public_rpc, call_service_rpc, delete_rows, get_public_rows, get_rows, get_service_json, patch_rows, patch_rows_no_response, post_rows, upsert_rows"
new_import = "from core.database import call_public_rpc, call_service_rpc, delete_rows, get_public_rows, get_rows, get_service_json, get_service_json_or_empty, patch_rows, patch_rows_ignoring_http_status, patch_rows_no_response, post_rows, upsert_rows"
if old_import in main:
    main = main.replace(old_import, new_import, 1)
elif new_import not in main:
    raise SystemExit("unexpected core.database import state")

main = main.replace("_sb_service_get(", "get_service_json_or_empty(")
main = main.replace("_sb_service_patch(", "patch_rows_ignoring_http_status(")
if "_sb_service_get" in main or "_sb_service_patch" in main:
    raise SystemExit("legacy service adapter reference remains")

compile(core, "core/database.py", "exec")
compile(main, "main.py", "exec")
core_path.write_text(core, encoding="utf-8")
main_path.write_text(main, encoding="utf-8")
