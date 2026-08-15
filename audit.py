#!/usr/bin/env python3
# ════════════════════════════════════════════════════════════════
# BROQUER — Auditor del contrato de diseño Canon
# Uso:  python3 audit.py [archivo.html ...]     (sin args: todos los .html)
#
# DESIGN.md define cómo se consume el sistema y brokr-theme.css es la única
# fuente ejecutable de valores. Este auditor comprueba reglas estructurales;
# deliberadamente NO mantiene otra copia de colores, radios o tipografías.
#
# Verifica las reglas que se pueden automatizar razonablemente:
#   1. Cero hex a mano (excepto #fff/#000 y marcas externas permitidas)
#   2. font-family solo var(--font-*) o inherit
#   3. font-size solo desde la escala --fs-*
#   4. border-radius / box-shadow solo desde tokens
#   5. Sin emojis como iconografía de interfaz
#   6. Sin texto ilegible usando tokens reservados a estados/decoración
#   7. Sin botones con fondo de tinta negra
#
# Exenciones reconocidas:
#   · Bloques  /* ═══ AUDIT-EXEMPT: razón ═══ */ ... /* ═══ /AUDIT-EXEMPT ═══ */
#   · Líneas con el marcador  AUDIT-EXEMPT-LINE: razón
#   · ★☆ como glifos de calificación (contenido, no icono; <option> no admite SVG)
#   · border-radius: 0  (reset válido)
#   · box-shadow inset de 1px (hairline técnico)
# ════════════════════════════════════════════════════════════════
import re, sys, glob, os

ALLOWED_HEX = {'#fff','#ffffff','#000','#000000','#25d366','#1877f2'}
SKIP = {'legal.html','aviso-privacidad.html','404.html','sitio.html','_TEMPLATE-modulo.html'}


def check_texto_ilegible(txt):
    """Impide usar tokens de muy bajo contraste como texto ordinario."""
    import re as _re
    bad = []
    for m in _re.finditer(r'([^{}]+)\{([^{}]*)\}', txt):
        sel = _re.sub(r'/\*.*?\*/', '', m.group(1), flags=_re.S).strip()
        if any(k in sel for k in ('placeholder',':disabled','svg','arrow','sep','.gap','ico','preview')):
            continue
        if _re.search(r'(?<!-)color:\s*var\((--mute-[23]|--line[\w-]*)\)', m.group(2)) or _re.search(r'--txt[\w-]*:\s*var\(--line', m.group(2)):
            bad.append(sel[:44])
    return bad


def check_botones_ink(txt):
    """La tinta negra es texto, no superficie de acción de un botón."""
    import re as _re
    bad = []
    for css in _re.findall(r'<style[^>]*>(.*?)</style>', txt, _re.S):
        for m in _re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
            sel = _re.sub(r'/\*.*?\*/', '', m.group(1), flags=_re.S).strip()
            if ('btn' not in sel and 'button' not in sel and '.fab' not in sel):
                continue
            if any(p in sel for p in (':hover',':active',':disabled')):
                continue
            if _re.search(r'background(?:-color)?\s*:\s*var\(--ink', m.group(2)):
                bad.append(sel[:44])
    return bad


def audit(path):
    txt = open(path, encoding='utf-8').read()
    t = re.sub(r'/\* ═+ AUDIT-EXEMPT.*?/AUDIT-EXEMPT ═+ \*/', '', txt, flags=re.S)
    t = '\n'.join(l for l in t.splitlines() if 'AUDIT-EXEMPT-LINE' not in l)
    ff = []
    for m in re.findall(r"font-family\s*:\s*([^;}\"'`]+)", t):
        v = m.replace('!important','').strip()
        if 'var(--font' not in v and v != 'inherit':
            ff.append(v[:50])
    br = []
    for m in re.findall(r'border-radius\s*:\s*([^;}]+)', t):
        v = m.replace('!important','').strip()
        if 'var(' not in v and '50%' not in v and v not in ('0','0px'):
            br.append(v[:40])
    bs = []
    for m in re.findall(r'box-shadow\s*:\s*([^;}]+)', t):
        v = m.strip()
        if 'var(' not in v and v.replace('!important','').strip() != 'none' and not v.startswith('inset 0 0 0 1px'):
            bs.append(v[:50])
    emoji = [e for e in re.findall('[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]', t) if e not in ('★','☆')]
    hexes = [h for h in (x.lower() for x in re.findall(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b', t)) if h not in ALLOWED_HEX]
    fs = re.findall(r'font-size\s*:\s*[\d.]+px', t)
    btn_ink = check_botones_ink(t)
    ilegible = check_texto_ilegible(t)
    css_ok = all(c.count('{')==c.count('}') for c in re.findall(r'<style[^>]*>(.*?)</style>', txt, re.S))
    return {
        'hex':hexes,
        'font-family':ff,
        'font-size-px':fs,
        'border-radius':br,
        'box-shadow':bs,
        'emoji':emoji,
        'boton-negro (usa tokens de acción/estructura)':btn_ink,
        'texto-ilegible (mute-2/3)':ilegible,
    }, css_ok


files = sys.argv[1:] or [f for f in sorted(glob.glob('*.html')) if os.path.basename(f) not in SKIP]
total = 0
for f in files:
    v, css_ok = audit(f)
    n = sum(len(x) for x in v.values())
    total += n
    mark = 'OK ' if n==0 and css_ok else 'X  '
    print(f'{mark}{os.path.basename(f):28} {n:3} violaciones' + ('' if css_ok else '  [CSS DESBALANCEADO]'))
    for k, items in v.items():
        if items:
            print(f'      {k}: {items[:6]}' + (f' (+{len(items)-6})' if len(items)>6 else ''))
print(f'\nTOTAL: {total} violaciones en {len(files)} archivos')
sys.exit(1 if total else 0)
