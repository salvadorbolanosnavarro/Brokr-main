from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

save_block = '''def save_config(data: dict):\n    try:\n        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))\n    except Exception:\n        pass\n\n'''
if save_block in source:
    source = source.replace(save_block, "", 1)
elif 'def save_config(' in source:
    raise SystemExit("unexpected save_config shape")

hmac_block = '''# ────────────────────────────────────────────\n# CONFIG — EB API KEY POR USUARIO (Supabase)\n# ────────────────────────────────────────────\n# Helper: compara dos secretos en tiempo constante (evita adivinarlos byte a\n# byte midiendo cuánto tarda la respuesta). Devuelve False si alguno va vacío.\ndef hmac_compare(recibido: str, esperado: str) -> bool:\n    import hmac as _h\n    if not recibido or not esperado:\n        return False\n    return _h.compare_digest(str(recibido), str(esperado))\n\n\n'''
if hmac_block in source:
    source = source.replace(hmac_block, "", 1)
elif 'def hmac_compare(' in source:
    raise SystemExit("unexpected hmac_compare shape")

for legacy in ('def save_config(', 'def hmac_compare('):
    if legacy in source:
        raise SystemExit(f"dead helper remains in main: {legacy}")
if 'def load_config() -> dict:' not in source or '_config = load_config()' not in source:
    raise SystemExit("legacy config.json read contract was altered")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
