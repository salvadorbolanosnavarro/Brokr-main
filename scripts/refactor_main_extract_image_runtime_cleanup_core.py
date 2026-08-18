from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

source = source.replace('import concurrent.futures\n', '')
source = source.replace('from PIL import Image, ImageEnhance\n', 'from PIL import Image\n')
opencv_block = '''# OpenCV\ntry:\n    import cv2\n    import numpy as np\n    CV2_AVAILABLE = True\nexcept ImportError:\n    CV2_AVAILABLE = False\n\n'''
source = source.replace(opencv_block, '')

for legacy in ('import concurrent.futures', 'import cv2', 'import numpy as np', 'CV2_AVAILABLE', 'ImageEnhance'):
    if legacy in source:
        raise SystemExit(f"dead image runtime symbol remains in main: {legacy}")
if 'from PIL import Image\n' not in source or 'PIL_AVAILABLE = True' not in source:
    raise SystemExit("Pillow compatibility needed by Facebook QA was removed")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
