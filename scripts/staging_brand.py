"""Presentation-only brand substitution for the existing staging build.

Keep source application code, identifiers, domains, data keys and integrations
unchanged. The supplied PNGs remain byte-for-byte originals inside SVG viewports.
"""
import re

WORDMARK = '/brand/comision-facil-wordmark.svg'
MONOGRAM = '/brand/comision-facil-monogram.svg'
TOUCH_ICON = '/brand/comision-facil-monogram-original.png'


def brand_asset(name, text):
    # A standalone commercial name, never identifiers, hosts, emails or paths.
    text = re.sub(r'(?:https?://|mailto:)[^\s\"\'<>`]+|(?<![\w@./-])Broquer(?![\w/-]|\.(?:app|com|png|svg|js))',
                  lambda match: 'Comisión Fácil' if match[0] == 'Broquer' else match[0], text)
    text = re.sub(r'(?<![\w@./-])Broq(?![\w/-]|\.(?:app|com|png|svg|js))', 'Cecil IA', text)
    if name == 'app-shell.js':
        # Name aliases only; retain existing voice activation behavior/aliases.
        text = text.replace('const WAKE = [', "const WAKE = ['cecil ia','cecil','oye cecil ia','oye cecil',", 1)
    if name.endswith(('.html', '.js')):
        text = text.replace('broquer<span>.</span>',
            '<picture class="cf-brand-picture"><source media="(max-width:720px)" '
            f'srcset="{MONOGRAM}"><img src="{WORDMARK}" alt="Comisión Fácil"></picture>')
        text = re.sub(r'(<span\b[^>]*class="bk-shk-mark"[^>]*>)b\.(</span>)',
                      rf'\1<img src="{MONOGRAM}" alt="">\2', text)
        # Home assistant tile uses the same brand initial without a class.
        text = text.replace('<span>b.</span>', f'<span><img class="cf-assistant-mark" src="{MONOGRAM}" alt=""></span>')
        text = text.replace('<strong>b.</strong>', f'<strong><img class="cf-assistant-mark" src="{MONOGRAM}" alt=""></strong>')
    images = {
        'logotipo-black.png': WORDMARK, 'logotipo-white.png': WORDMARK,
        'logo-broquer.png': WORDMARK, 'logo-broquer-blanco.png': WORDMARK,
        'logotipo-broquer.png': WORDMARK, 'logotipo.png': WORDMARK,
        'logotipo-brokr.svg': WORDMARK,
        'isotipo-black.png': MONOGRAM, 'isotipo-white.png': MONOGRAM,
        'broq-icon.png': MONOGRAM, 'favicon.png': MONOGRAM,
        'favicon.svg': MONOGRAM, 'icon-192.png': MONOGRAM, 'icon-512.png': MONOGRAM,
    }
    for old, new in images.items():
        text = re.sub(r'(?<![\w/-])(?:\.\./|\./|/)?' + re.escape(old) + r'(?![\w.-])', new, text)
    if name.endswith('.html'):
        text = re.sub(r'(<link\b[^>]*rel="icon"[^>]*type=")image/png', r'\1image/svg+xml', text)
        text = re.sub(r'(<link\b[^>]*rel="apple-touch-icon"[^>]*href=")[^"]+', rf'\1{TOUCH_ICON}', text)
        text = text.replace('</head>', '<link rel="stylesheet" href="/brand/staging-brand.css">\n</head>', 1)
    return text
