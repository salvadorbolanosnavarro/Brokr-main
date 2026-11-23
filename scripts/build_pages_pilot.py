"""GitHub Pages artifact: unchanged Broquer assets plus the private Cecil UI pilot.

Copy tracked web assets only. Backend code, SQL, tests, credentials and local
backups must never enter the publication artifact.
"""
import argparse
from pathlib import Path
import shutil
from scripts.build_cecil_canary import ROOT, build, git

WEB_SUFFIXES = {'.html','.js','.css','.svg','.png','.jpg','.jpeg','.webp','.ico',
                '.woff','.woff2','.ttf','.gif','.mp4','.webm','.pdf'}
WEB_FOLDERS = {'ui','videos','brand','fonts','styles','vendor'}

def package(output):
    output=Path(output).resolve()
    if output.exists() or output==ROOT:
        raise ValueError('Use a new output directory')
    output.mkdir(parents=True)
    for name in git('ls-files').decode().splitlines():
        relative=Path(name)
        if name not in {'CNAME','.nojekyll','manifest.json'}:
            if relative.suffix.lower() not in WEB_SUFFIXES:continue
            if len(relative.parts)>1 and relative.parts[0] not in WEB_FOLDERS:continue
            if relative.name.startswith('_'):continue
        source=ROOT/relative
        if not source.is_file() or source.is_symlink():
            raise ValueError('Missing or unsafe tracked asset: '+name)
        target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
    build(output/'cecil')
    assert (output/'index.html').read_bytes()==(ROOT/'index.html').read_bytes()
    assert (output/'CNAME').read_text().strip()=='broquer.app'
    for path in output.rglob('*'):
        if path.is_file() and path.suffix.lower() in {'.py','.sql','.env'}:
            raise ValueError('Backend/private file in publication artifact')
    print('GitHub Pages: original Broquer assets retained; Cecil added separately.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    package(parser.parse_args().output)
