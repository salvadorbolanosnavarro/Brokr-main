from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "brokr-theme.css"
IMPORT = '@import url("sidebar-interactions.css");'
ANCHOR = "@import url('https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..800&display=swap');"

text = THEME.read_text(encoding="utf-8")
if IMPORT in text:
    print("sidebar interaction import already present")
else:
    if ANCHOR not in text:
        raise RuntimeError("brokr-theme.css: deterministic Google Fonts import anchor not found")
    text = text.replace(ANCHOR, ANCHOR + "\n" + IMPORT, 1)
    THEME.write_text(text, encoding="utf-8")
    print("inserted sidebar interaction import")
