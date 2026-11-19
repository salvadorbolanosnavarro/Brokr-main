"""Package audited static output for the existing Pages project's root deployment.

No provider settings or variables are changed. Advanced-mode routing exposes only
this allowlisted artifact, never the repository's production frontend or backend.
"""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (b'api.broquer.app', b'urtgysmtnvoqaljuhntz')


def audit(directory):
    files = sorted(path for path in directory.rglob('*') if path.is_file())
    if not files:
        raise ValueError('Empty preview output')
    manifest = {}
    for path in files:
        if path.suffix.lower() in {'.py','.pyc','.sql','.env'} or '__pycache__' in path.parts:
            raise ValueError(f'Non-public source in artifact: {path}')
        payload = path.read_bytes()
        if any(word in payload.lower() for word in FORBIDDEN):
            raise ValueError(f'Production reference in published file: {path.relative_to(directory)}')
        manifest[path.relative_to(directory).as_posix()] = hashlib.sha256(payload).hexdigest()
    return manifest


def package():
    source = ROOT / 'dist'
    manifest = audit(source)
    output = ROOT / 'preview-public'
    if output.exists(): shutil.rmtree(output)
    shutil.copytree(source, output)
    (ROOT/'preview-public-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Packaged {len(manifest)} audited public assets; no production references.')


if __name__ == '__main__': package()
