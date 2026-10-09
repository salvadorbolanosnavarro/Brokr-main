"""Build only tracked public assets for the existing broquer-staging Pages project."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PROD_DB = 'https://urtgysmtnvoqaljuhntz.supabase.co'
PROD_KEY = 'sb_publishable_EVGLfmHVorBpQQWAh-vypA_hANNk_-i'
BRANCH = 'work/redesign-preview-20261003'

def config(env):
    if env.get('CF_PAGES_BRANCH', BRANCH) != BRANCH:
        raise ValueError('This build is exclusively for PR #180, never main.')
    api = env.get('BROQUER_STAGING_API_URL', '').rstrip('/')
    db = env.get('BROQUER_STAGING_SUPABASE_URL', '').rstrip('/')
    key = env.get('BROQUER_STAGING_SUPABASE_KEY', '').strip()
    if api != 'https://brokr-main-staging.up.railway.app':
        raise ValueError('Use the existing Railway staging backend.')
    parsed = urlsplit(db)
    if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.supabase.co') or parsed.path or parsed.query or parsed.username or db == PROD_DB:
        raise ValueError('A separate Supabase staging project URL is required.')
    if not key or key == PROD_KEY or key.startswith('sb_secret_'):
        raise ValueError('Only the public key of the separate staging project is allowed.')
    if not key.startswith('sb_publishable_'):
        try:
            payload = json.loads(base64.urlsafe_b64decode(key.split('.')[1] + '==='))
        except Exception as exc:
            raise ValueError('Invalid Supabase public key') from exc
        if payload.get('role') != 'anon' or payload.get('ref') != parsed.hostname.split('.')[0]:
            raise ValueError('JWT must be anon and match the staging project.')
    return api, db, key

def build(env=os.environ):
    api, db, key = config(env)
    output = ROOT / 'dist'
    if output.exists(): shutil.rmtree(output)
    allowed = {'.html','.js','.css','.json','.svg','.png','.jpg','.jpeg','.webp','.gif','.ico','.woff','.woff2','.ttf','.otf','.mp4','.webm','.pdf'}
    excluded = {'scripts','tests','core','routers','ios','.github','supabase','staging','test-results','cloudflare'}
    paths = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    count = 0
    for name in sorted(set(paths)):
        p = Path(name)
        if p.parts[0] in excluded or p.suffix.lower() not in allowed or name == 'redesign-inventory.json': continue
        source = ROOT / p
        if not source.is_file(): continue
        target = output / p
        target.parent.mkdir(parents=True,exist_ok=True)
        if p.suffix in {'.html','.js','.css','.json','.svg'}:
            text = source.read_text()
            for old,new in [('https://api.broquer.app',api),(PROD_DB,db),(PROD_KEY,key)]: text = text.replace(old,new)
            text = text.replace('api.broquer.app',urlsplit(api).hostname).replace('urtgysmtnvoqaljuhntz.supabase.co',urlsplit(db).hostname)
            if p.suffix == '.html' and 'styles/mobile-inputs.css' not in text:
                prefix = '../' * (len(p.parts)-1)
                text = text.replace('</head>',f'<link rel="stylesheet" href="{prefix}styles/mobile-inputs.css">\n</head>')
            if 'api.broquer.app' in text or 'urtgysmtnvoqaljuhntz.supabase.co' in text or PROD_KEY in text:
                raise ValueError(f'Production API reference remains in {name}')
            target.write_text(text)
        else: shutil.copyfile(source,target)
        count += 1
    # connect-src applies even to old inline code: no production DB/API writes.
    (output / '_headers').write_text(f'''/*
  X-Robots-Tag: noindex, nofollow
  Referrer-Policy: strict-origin-when-cross-origin
  Content-Security-Policy: connect-src 'self' {api} {db} wss://{urlsplit(db).hostname}; object-src 'none'; base-uri 'self'
''')
    print(f'Staging build: {count} public assets. No backend, SQL or secret files included.')

if __name__ == '__main__': build()
