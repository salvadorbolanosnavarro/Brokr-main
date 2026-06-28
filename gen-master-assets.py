#!/usr/bin/env python3
# Genera el icon master 1024x1024 y el splash master 2732x2732 para iOS.
# Fondo: #FFFFFF (tema Skyscanner). Sin alpha (Apple rechaza transparencia en icono App Store).
from PIL import Image
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "assets"
OUT.mkdir(parents=True, exist_ok=True)

BRAND = (255, 255, 255)  # #FFFFFF (tema Skyscanner)

def composite(src_path, out_path, canvas, iso_pct):
    iso = Image.open(src_path).convert("RGBA")
    target = int(canvas * iso_pct)
    # Mantén aspect ratio
    w, h = iso.size
    scale = target / max(w, h)
    iso = iso.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    bg = Image.new("RGB", (canvas, canvas), BRAND)
    x = (canvas - iso.size[0]) // 2
    y = (canvas - iso.size[1]) // 2
    bg.paste(iso, (x, y), mask=iso)
    bg.save(out_path, "PNG", optimize=True)
    print(f"✔ {out_path.name}  {canvas}x{canvas}")

composite(SRC / "isotipo-black.png", OUT / "icon.png", 1024, 0.62)
composite(SRC / "isotipo-black.png", OUT / "splash.png", 2732, 0.22)
composite(SRC / "isotipo-black.png", OUT / "splash-dark.png", 2732, 0.22)
