"""Build only tracked public assets for the existing broquer-staging Pages project."""
import base64
import io
import re
import tarfile
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit
try:
    from staging_brand import brand_asset, write_brand_artwork, MONOGRAM
except ModuleNotFoundError:
    from scripts.staging_brand import brand_asset, write_brand_artwork, MONOGRAM

ROOT = Path(__file__).resolve().parents[1]
PROD_DB = 'https://urtgysmtnvoqaljuhntz.supabase.co'
PROD_KEY = 'sb_publishable_EVGLfmHVorBpQQWAh-vypA_hANNk_-i'
BRANCH = 'work/cecil-staging-preview-20261119'

def config(env):
    if env.get('CF_PAGES_BRANCH') != BRANCH:
        raise ValueError('This preview is exclusively for the Cecil staging preview branch, never main.')
    mode = env.get('BROQUER_STAGING_MODE', 'connected')
    if mode != 'connected':
        raise ValueError('Cecil preview requires connected staging mode')
    api = env.get('BROQUER_STAGING_API_URL', '').rstrip('/')
    db = env.get('BROQUER_STAGING_SUPABASE_URL', '').rstrip('/')
    key = env.get('BROQUER_STAGING_SUPABASE_KEY', '').strip()
    if api != 'https://brokr-main-staging.up.railway.app':
        raise ValueError('Use the existing Railway staging backend.')
    parsed = urlsplit(db)
    if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.supabase.co') or parsed.path or parsed.query or parsed.username or db != 'https://tymhlvawnqadqgwnpruk.supabase.co':
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
    # Config validates the existing public staging variables; never change them.
    api, db, key = config(env)
    import tempfile
    try:
        from scripts.build_cecil_canary import build as build_cecil
    except ModuleNotFoundError:
        import sys
        sys.path.insert(0, str(ROOT))
        from scripts.build_cecil_canary import build as build_cecil
    output = ROOT / 'dist'
    if output.exists(): shutil.rmtree(output)
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / 'cecil'
        build_cecil(source, staging=True)
        shutil.copytree(source, output / 'cecil')
        # The baseline UI is real Broquer, wired only to the staging services.
        # It is the fallback used to rehearse the pilot, never production data.
        from scripts.build_cecil_canary import BASE_REF, EXTENSIONS, FOLDERS
        archive=tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive',BASE_REF],cwd=Path(__file__).resolve().parents[1])))
        for entry in archive:
            relative=Path(entry.name)
            if not entry.isfile():continue
            if not ((len(relative.parts)==1 or relative.parts[0] in FOLDERS) and (relative.suffix.lower() in EXTENSIONS or str(relative)=='manifest.json')):continue
            target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.extractfile(entry).read())
    for path in output.rglob('*'):
        if not path.is_file() or path.suffix not in {'.html','.js','.css','.json','.svg'}: continue
        text=path.read_text()
        if path.name == 'app-shell.js':
            # Do not send staging errors through the inherited production loader.
            text=re.sub(r'  \(function initSentry\(\) \{.*?  /\* ── Config', '  /* ── Config', text, count=1, flags=re.S)
            marker='    if (!profile) return; // redirected to login/landing'
            if marker not in text:raise ValueError('Missing shared auth hook')
            text=text.replace(marker,marker+"\n    const pilot=document.createElement('script');pilot.src='/staging-pilot.js';pilot.onload=()=>window.bkCecilRollout?.({api:location.origin,token:getToken(),userId:profile.user.id});document.head.appendChild(pilot);",1)
        if path.name == 'propiedades.html':
            # The redesigned modal footer is outside the form. SubmitEvent
            # still identifies its button; preserve legacy in-form fallback.
            text=text.replace("const btn = form.querySelector('.pf-save-btn');", "const btn = e.submitter || form.querySelector('.pf-save-btn') || document.querySelector('.pf-save-btn[form=\"prop-form\"]');")
        for old,new in [('https://api.broquer.app',api),(PROD_DB,db),(PROD_KEY,key)]: text=text.replace(old,new)
        text=text.replace('api.broquer.app',urlsplit(api).hostname).replace('urtgysmtnvoqaljuhntz.supabase.co',urlsplit(db).hostname)
        if 'api.broquer.app' in text or 'urtgysmtnvoqaljuhntz' in text or PROD_KEY in text:
            raise ValueError(f'Production reference remains: {path.relative_to(output)}')
        path.write_text(re.sub(r'[ \t]+$', '', text, flags=re.M))
    (output/'staging-pilot.js').write_bytes((Path(__file__).resolve().parent/'staging_pilot_client.js').read_bytes())
    audit_script=ROOT/'scripts/staging_network_audit.js'
    if audit_script.exists():
        (output/'staging-network-audit.js').write_bytes(audit_script.read_bytes())
        for page in output.rglob('*.html'):
            page.write_text(page.read_text().replace('</head>','<script src="/staging-network-audit.js" defer></script>\n</head>',1))
    connections=f"'self' {api} {db} wss://{urlsplit(db).hostname} https://o4511509854945280.ingest.us.sentry.io"
    (output/'_headers').write_text(f"/*\n  X-Robots-Tag: noindex, nofollow\n  Content-Security-Policy: connect-src {connections}; object-src 'none'; base-uri 'self'\n")
    (output/'preview-release.json').write_text(json.dumps({'source_pr':217,'design': '086fd40e7953439eceb17822abca7e29aea4bd8e','mode':'staging-preview','api':api,'database_ref':urlsplit(db).hostname.split('.')[0]},indent=2))
    print('Cecil preview built with staging services exclusively.')

if __name__ == '__main__': build()
