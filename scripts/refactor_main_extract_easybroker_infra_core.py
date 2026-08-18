from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

import_anchor = '''from core.cache import cache_get, cache_set\n'''
import_line = '''from core.easybroker import EB_API_KEY, EB_BASE, eb_headers\n'''
if source.count(import_line) == 0:
    if source.count(import_anchor) != 1:
        raise SystemExit("unexpected EasyBroker Core import anchor")
    source = source.replace(import_anchor, import_anchor + import_line, 1)
elif source.count(import_line) != 1:
    raise SystemExit("unexpected EasyBroker Core import state")

config_block = '''CONFIG_FILE = Path(__file__).parent / "config.json"\n\ndef load_config() -> dict:\n    try:\n        if CONFIG_FILE.exists():\n            return json.loads(CONFIG_FILE.read_text())\n    except Exception:\n        pass\n    return {}\n\n_config = load_config()\n\n'''
if config_block in source:
    source = source.replace(config_block, "", 1)
elif 'CONFIG_FILE = Path(__file__).parent / "config.json"' in source or 'def load_config() -> dict:' in source:
    raise SystemExit("unexpected legacy EasyBroker config shape")

for line in (
    'EB_API_KEY       = settings.easybroker_api_key or _config.get("eb_api_key", "")\n',
    'EB_BASE          = "https://api.easybroker.com/v1"\n',
):
    if line in source:
        source = source.replace(line, "", 1)
    elif line.strip() in source:
        raise SystemExit(f"unexpected EasyBroker global shape: {line.strip()}")

eb_headers_block = '''def eb_headers(key: str = None):\n    k = key or EB_API_KEY\n    return {"X-Authorization": k, "accept": "application/json"}\n\n'''
if eb_headers_block in source:
    source = source.replace(eb_headers_block, "", 1)
elif 'def eb_headers(' in source:
    raise SystemExit("unexpected eb_headers shape")

for legacy in (
    'CONFIG_FILE = Path(__file__).parent / "config.json"',
    'def load_config() -> dict:',
    '_config = load_config()',
    'EB_API_KEY       = settings.easybroker_api_key',
    'EB_BASE          = "https://api.easybroker.com/v1"',
    'def eb_headers(',
):
    if legacy in source:
        raise SystemExit(f"EasyBroker compatibility symbol remains in main: {legacy}")
if source.count(import_line) != 1:
    raise SystemExit("Core EasyBroker import not present exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
