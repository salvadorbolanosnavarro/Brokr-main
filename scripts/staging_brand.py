"""Presentation-only brand substitution for the existing staging build.

Keep source application code, identifiers, domains, data keys and integrations
unchanged. Web artwork is exported from the supplied logos.
"""
import re
import base64

WORDMARK = '/brand/cecil-wordmark.webp'
ASSISTANT = '/brand/cecil-assistant.webp'
MONOGRAM = '/brand/cecil-icon.svg'
TOUCH_ICON = '/brand/cecil-icon.png'


def write_brand_artwork(root, output):
    """Embed the platform's compact icon for favicon and manifest use."""
    source = root / TOUCH_ICON.lstrip('/')
    if not source.is_file():
        return  # Minimal build fixtures may not include brand assets.
    data = base64.b64encode(source.read_bytes()).decode('ascii')
    target = output / MONOGRAM.lstrip('/')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 180" '
                      f'role="img" aria-label="Cecil"><image width="180" height="180" '
                      f'href="data:image/png;base64,{data}"/></svg>\n')


def brand_asset(name, text):
    # A standalone commercial name, never identifiers, hosts, emails or paths.
    text = re.sub(r'(?:https?://|mailto:)[^\s\"\'<>`]+|(?<![\w@./-])Broquer(?![\w/-]|\.(?:app|com|png|svg|js))',
                  lambda match: 'Cecil' if match[0] == 'Broquer' else match[0], text)
    text = re.sub(r'(?<![\w@./-])Broq(?![\w/-]|\.(?:app|com|png|svg|js))', 'Cecil IA', text)
    if name == 'app-shell.js':
        # Name aliases only; retain existing voice activation behavior/aliases.
        text = text.replace('const WAKE = [', "const WAKE = ['cecil ia','cecil','oye cecil ia','oye cecil',", 1)
    if name.endswith(('.html', '.js')):
        text = text.replace('broquer<span>.</span>',
            '<picture class="cf-brand-picture"><source media="(max-width:720px)" '
            f'srcset="{WORDMARK}"><img src="{WORDMARK}" alt="Cecil"></picture>')
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
        'broq-icon.png': ASSISTANT, 'favicon.png': MONOGRAM,
        'favicon.svg': MONOGRAM, 'icon-192.png': MONOGRAM, 'icon-512.png': MONOGRAM,
    }
    for old, new in images.items():
        text = re.sub(r'(?<![\w/-])(?:\.\./|\./|/)?' + re.escape(old) + r'(?![\w.-])', new, text)
    if name == 'app-shell.js':
        text = text.replace('<div class="bk-shk-name">Cecil IA</div>',
            f'<div class="bk-shk-name"><img class="cecil-assistant-logo" src="{ASSISTANT}" alt="Cecil IA"></div>')
    if name == 'landing.html':
        # The legacy decorative reel has the previous logo baked into its frames.
        text = re.sub(r'<video[^>]+poster="animacion-broquer\.png"[^>]*>.*?</video>',
            f'<img class="cecil-hero-logo" src="{WORDMARK}" alt="Cecil">', text, count=1, flags=re.S)
    if name.endswith('.html'):
        text = re.sub(r'(<link\b[^>]*rel="icon"[^>]*type=")image/png', r'\1image/svg+xml', text)
        text = re.sub(r'(<link\b[^>]*rel="apple-touch-icon"[^>]*href=")[^"]+', rf'\1{TOUCH_ICON}', text)
        text = text.replace('</head>', '<link rel="stylesheet" href="/brand/staging-brand.css"><link rel="stylesheet" href="/ui/refinement.css"><script defer src="/ui/iconography.js"></script>\n</head>', 1)
    return text
