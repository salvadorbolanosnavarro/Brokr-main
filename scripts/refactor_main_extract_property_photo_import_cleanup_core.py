from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")
line = 'from core.property_photos import FOTOS_BUCKET as _FOTOS_BUCKET\n'
if source.count(line) != 1:
    raise SystemExit(f"expected one dead property-photo import, found {source.count(line)}")
source = source.replace(line, '', 1)
if '_FOTOS_BUCKET' in source:
    raise SystemExit('property photo bucket symbol still used in main')
compile(source, 'main.py', 'exec')
path.write_text(source, encoding='utf-8')
