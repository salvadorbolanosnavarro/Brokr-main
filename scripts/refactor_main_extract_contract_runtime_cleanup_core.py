from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

source = source.replace('from core.executors import _thread_pool\n', '')
source = source.replace('from fastapi.responses import FileResponse\n', '')
source = source.replace('import tempfile, os, subprocess, json as _json\n', 'import os, json as _json\n')

for legacy in (
    'from core.executors import _thread_pool',
    'from fastapi.responses import FileResponse',
    'tempfile',
    'subprocess',
):
    if legacy in source:
        raise SystemExit(f"dead contract runtime symbol remains in main: {legacy}")

for required in ('import os, json as _json', '_json.loads('):
    if required not in source:
        raise SystemExit(f"live runtime dependency was removed: {required}")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
