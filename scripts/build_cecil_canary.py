"""Build a real-service Cecil alternative, never the staging/demo compilation.

Run from a full Git checkout after normal production asset preparation. The
pinned design commit must contain the production base; fail rather than silently
shipping outdated application behavior when production advances.
"""
import argparse
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# Production polish on branch cecil/produccion-pulido (built on design
# df49373 = 3776420 + ACM hidden, base 2a1f4f5): tokens, shared heading,
# mobile tab bar, transparent monogram and the Inicio/Agenda/Estadísticas/
# Inmuebles fixes, fixed bottom sheets on phones (cecil/movil-hojas) and the
# centered floating action (cecil/movil-fab) and the hola@cecilapp.co contact
# (cecil/correo-cecilapp). Previous: 524b87d, 2a8a51f, 60aa01e, df49373.
DESIGN_REF = '1147fd288a4a070f85a9b67cc54139d8b3ba8ae0'
BASE_REF = '2a1f4f58f9cfa6df772c8956a1dc09f5ab72c56d'
EXTENSIONS = {'.html', '.js', '.css', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.ico', '.woff', '.woff2', '.ttf', '.gif', '.mp4', '.webm'}
FOLDERS = {'brand', 'fonts', 'ui', 'styles', 'vendor', 'videos'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def build(output):
    output = Path(output).resolve()
    if output == ROOT or output.name != 'cecil' or output.exists():
        raise ValueError('Use a new output directory named cecil; never overwrite an existing release.')
    if subprocess.run(['git','merge-base','--is-ancestor', BASE_REF, DESIGN_REF],cwd=ROOT).returncode:
        raise ValueError('Design does not include the production base.')
    # Root app changes beyond this pilot must be explicitly integrated first.
    for ref in [BASE_REF, DESIGN_REF]: git('rev-parse', '--verify', ref+'^{commit}')
    allowed_changes={'app-shell.js','main.py','core/config.py','routers/cecil_ui.py','ui/cecil-rollout.js','scripts/build_cecil_canary.py','scripts/cecil_mobile_fields.css','tests/test_cecil_ui.py','tests/check_cecil_rollout.cjs','CECIL_PILOT.md','tests/check_cecil_pilot_state.cjs','.github/workflows/quality.yml','tests/golden/http_contract_effective.json'}
    allowed_changes.update({'scripts/build_pages_pilot.py','.github/workflows/pages-pilot.yml','ui/cecil-error-probe.js','tests/check_cecil_error_probe.cjs'})
    # CI-only: the staging sync runs this builder's tests on the source tree (#228).
    allowed_changes.add('.github/workflows/sync-main-a-staging.yml')
    # Backend-only CORS list (cecilapp.co): never part of the Cecil artifact.
    allowed_changes.update({'core/cors.py','tests/test_cors_modes.py','cloudflare/cecil-app-worker.js'})
    # Server-side document branding (Cecil asks for brand=cecil): backend only.
    allowed_changes.update({'core/marca_documentos.py','core/marca_assets/cecil-wordmark.png','routers/ficha_pdf_renderer.py','routers/finanzas.py','tests/test_marca_documentos.py'})
    # Backend-only atomic self-delete fix + its test and SQL check: never part of the Cecil artifact.
    allowed_changes.update({'routers/account_delete.py','tests/test_main_self_account_delete_core_refactor.py','sql-manual/20261128-usuarios-huerfanos.sql'})
    changed=set(git('diff','--name-only',BASE_REF,'HEAD').decode().splitlines())
    if changed - allowed_changes:
        raise ValueError('Production advanced: integrate it into the design snapshot and update the pinned base before building.')
    archive = tarfile.open(fileobj=io.BytesIO(git('archive',DESIGN_REF)))
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp)
        for entry in archive:
            path=Path(entry.name)
            if not entry.isfile(): continue
            keep = (len(path.parts)==1 or path.parts[0] in FOLDERS) and (path.suffix.lower() in EXTENSIONS or str(path)=='manifest.json')
            if keep or str(path)=='scripts/staging_brand.py':
                target=source/path; target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.extractfile(entry).read())
        spec=importlib.util.spec_from_file_location('cecil_brand',source/'scripts/staging_brand.py')
        brand=importlib.util.module_from_spec(spec);spec.loader.exec_module(brand)
        try:
            output.mkdir(parents=True)
            pages=[]
            for path in source.rglob('*'):
                if not path.is_file() or path.parts[-2]=='scripts':continue
                relative=path.relative_to(source)
                # No demo runtime, test fixtures, API rewriting or staging guard.
                if path.name in {'demo-runtime.js','staging-auth-guard.js'}:continue
                target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
                if path.suffix in {'.html','.js','.css','.json','.svg'}:
                    text=path.read_text()
                    if path.suffix in {'.html','.js','.json','.svg'} and relative.parts[0]!='brand':text=brand.brand_asset(str(relative),text)
                    if relative==Path('app-shell.js'):
                        # Exact mobile fix approved in PR220: size before focus,
                        # retain native pinch, remove the legacy scale reset.
                        text, removed = re.subn(
                            r'/\* ── Guarda de escala en iOS .*?(?=/\* ── El teclado de iPhone)',
                            '/* Mobile fields prevent focus auto-zoom; native pinch zoom remains enabled. */\n\n',
                            text, count=1, flags=re.S)
                        if removed != 1:
                            raise ValueError('Missing legacy pinch-zoom guard: review the approved transformation')
                        marker='    if (!profile) return; // redirected to login/landing'
                        if marker not in text:raise ValueError('Missing shell authentication hook')
                        text=text.replace(marker,marker+"\n    const rollout=document.createElement('script');rollout.src='/ui/cecil-rollout.js';rollout.onload=()=>window.bkCecilRollout?.({api:API_BASE,getToken,userId:profile.user.id});document.head.appendChild(rollout);",1)
                    if relative==Path('propiedades.html'):
                        # Approved modal footer is outside the form in this design.
                        text=text.replace("const btn = form.querySelector('.pf-save-btn');", "const btn = e.submitter || form.querySelector('.pf-save-btn') || document.querySelector('.pf-save-btn[form=\"prop-form\"]');")
                    # Keep assets and relative navigation within the alternate build.
                    text=re.sub(r'(["\'])/(brand|ui|styles|fonts)/',r'\1/cecil/\2/',text)
                    text=text.replace("rollout.src='/cecil/ui/cecil-rollout.js'", "rollout.src='/ui/cecil-rollout.js'")
                    if path.suffix=='.html':
                        def mobile_meta(match):
                            def content(value):
                                parts = [part.strip() for part in value.group(2).split(',')
                                         if part.strip().split('=')[0].strip().lower()
                                         not in {'maximum-scale', 'minimum-scale', 'user-scalable'}]
                                return value.group(1) + ','.join(parts) + value.group(3)
                            return re.sub(r'(content=["\'])(.*?)(["\'])', content, match.group(0), flags=re.I)
                        text = re.sub(r'<meta\b[^>]*name=["\']viewport["\'][^>]*>', mobile_meta, text, flags=re.I)
                        text = text.replace('</head>', '<link rel="stylesheet" href="/cecil/mobile-fields.css"/>\n</head>', 1)
                        pages.append(str(relative))
                    target.write_text(text)
                else:target.write_bytes(path.read_bytes())
            brand.write_brand_artwork(source,output)
            (output/'mobile-fields.css').write_bytes((ROOT/'scripts/cecil_mobile_fields.css').read_bytes())
            (output/'release.json').write_text(json.dumps({'production_base':git('rev-parse',BASE_REF).decode().strip(),'design':git('rev-parse',DESIGN_REF).decode().strip(),'mode':'real-services','pages':pages},indent=2))
        except Exception:
            import shutil
            shutil.rmtree(output)
            raise
    print(f'Cecil pilot: {len(pages)} pages, production services retained, demo runtime excluded: {output}')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'dist/cecil'));build(parser.parse_args().output)
