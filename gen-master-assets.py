#!/usr/bin/env python3
# Genera el icon master 1024x1024 y el splash master 2732x2732 para iOS.
# Icono: fondo #F7F5EE (marca). Splash/intro: fondo #FFFFFF (blanco puro).
# Sin alpha (Apple rechaza transparencia en icono App Store).
from PIL import Image
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "assets"
OUT.mkdir(parents=True, exist_ok=True)

BRAND_ICON   = (247, 245, 238)  # #F7F5EE — ícono de la app
BRAND_SPLASH = (255, 255, 255)  # #FFFFFF — splash / intro

def composite(src_path, out_path, canvas, iso_pct, bg_color):
    iso = Image.open(src_path).convert("RGBA")
    target = int(canvas * iso_pct)
    # Mantén aspect ratio
    w, h = iso.size
    scale = target / max(w, h)
    iso = iso.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    bg = Image.new("RGB", (canvas, canvas), bg_color)
    x = (canvas - iso.size[0]) // 2
    y = (canvas - iso.size[1]) // 2
    bg.paste(iso, (x, y), mask=iso)
    bg.save(out_path, "PNG", optimize=True)
    print(f"✔ {out_path.name}  {canvas}x{canvas}")

composite(SRC / "isotipo-black.png", OUT / "icon.png", 1024, 0.62, BRAND_ICON)
composite(SRC / "logotipo-black.png", OUT / "splash.png", 2732, 0.34, BRAND_SPLASH)
composite(SRC / "logotipo-black.png", OUT / "splash-dark.png", 2732, 0.34, BRAND_SPLASH)
