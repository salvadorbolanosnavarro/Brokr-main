from pathlib import Path

path = Path("core/database.py")
source = path.read_text(encoding="utf-8")

marker = '''async def post_rows(\n'''
new_block = '''async def call_service_rpc(\n    function: str,\n    payload: Mapping[str, Any],\n    *,\n    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,\n    accepted_statuses: tuple[int, ...] | None = None,\n) -> Any:\n    """Call a Supabase RPC with service-role credentials and raw JSON semantics."""\n    async with httpx.AsyncClient(timeout=timeout) as client:\n        response = await client.post(\n            rpc_url(function),\n            headers=service_headers(),\n            json=dict(payload),\n        )\n    _require_response_status(response, accepted_statuses)\n    return response.json()\n\n\n'''

if source.count("async def call_service_rpc(") == 0:
    if source.count(marker) != 1:
        raise SystemExit("unexpected post_rows marker state")
    source = source.replace(marker, new_block + marker, 1)
elif source.count("async def call_service_rpc(") != 1:
    raise SystemExit("unexpected call_service_rpc state")

compile(source, "core/database.py", "exec")
path.write_text(source, encoding="utf-8")
