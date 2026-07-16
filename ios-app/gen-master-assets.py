#!/usr/bin/env python3
# =============================================================================
# Broquer · Genera el icon master 1024x1024 y el splash master 2732x2732 (iOS).
#
# ESTE ES EL ÚNICO LUGAR QUE DEFINE EL ICONO DE LA APP.
# La fuente es isotipo-black.png (raíz del repo). De ahí Codemagic saca los
# 21 tamaños que Apple pide, incluido el de 1024 que se ve en el App Store.
# Editar los PNG de AppIcon.appiconset a mano NO sirve: este script los pisa
# en cada build.
#
# Dos cosas que importan y que antes estaban mal:
#
#  1) MARGEN. isotipo-black.png trae margen transparente alrededor de la B.
#     Antes se escalaba usando el lienzo completo (margen incluido), así que
#     la B salía más chica de lo pedido: se pedía 62% y aterrizaba en 48%.
#     Ahora el script RECORTA el margen solo y encuadra sobre la tinta real,
#     así el porcentaje de abajo es el que de verdad se ve.
#
#  2) ALPHA. Apple rechaza el icono de 1024 si trae canal de transparencia
#     (error ITMS-90717). Todo se guarda en RGB, sin alpha, a propósito.
# =============================================================================
from PIL import Image
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "assets"
OUT.mkdir(parents=True, exist_ok=True)

FUENTE = SRC / "isotipo-black.png"

BLANCO = (255, 255, 255)   # fondo del icono de la app
BONE   = (247, 245, 238)   # #F7F5EE — fondo del splash (color de marca)

# Qué tanto del lienzo ocupa la B (medido sobre la tinta, ya sin margen).
ICON_PCT   = 0.55    # icono: mismo encuadre que el master aprobado
SPLASH_PCT = 0.172   # splash: idéntico a como se veía antes


def recorta(im):
    """Quita el margen transparente para encuadrar sobre la B de verdad."""
    caja = im.getbbox()
    return im.crop(caja) if caja else im


def compone(src_path, out_path, lienzo, pct, fondo):
    iso = recorta(Image.open(src_path).convert("RGBA"))
    objetivo = int(lienzo * pct)
    w, h = iso.size
    escala = objetivo / max(w, h)
    iso = iso.resize((max(1, round(w * escala)), max(1, round(h * escala))), Image.LANCZOS)

    # RGB (no RGBA): el icono del App Store NO puede llevar alpha.
    bg = Image.new("RGB", (lienzo, lienzo), fondo)
    bg.paste(iso, ((lienzo - iso.size[0]) // 2, (lienzo - iso.size[1]) // 2), mask=iso)
    bg.save(out_path, "PNG", optimize=True)
    print(f"✔ {out_path.name}  {lienzo}x{lienzo}  (B al {pct*100:.0f}%, fondo {fondo}, sin alpha)")


if not FUENTE.exists():
    raise SystemExit(f"✖ No encuentro {FUENTE}. Ese archivo ES el icono de la app.")

compone(FUENTE, OUT / "icon.png",         1024, ICON_PCT,   BLANCO)
compone(FUENTE, OUT / "splash.png",       2732, SPLASH_PCT, BONE)
compone(FUENTE, OUT / "splash-dark.png",  2732, SPLASH_PCT, BONE)
