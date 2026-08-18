from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

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
    'EB_API_KEY       =',
    'EB_BASE          = "https://api.easybroker.com/v1"',
    'def eb_headers(',
):
    if legacy in source:
        raise SystemExit(f"dead EasyBroker global remains in main: {legacy}")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
