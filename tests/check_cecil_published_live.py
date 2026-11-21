"""Opt-in read-only audit of EVERY publicly routed preview file."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import subprocess
import tempfile
import json
from pathlib import Path
from urllib.parse import urlsplit, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

parser=argparse.ArgumentParser()
parser.add_argument('--origin',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
if not urlsplit(args.origin).hostname.endswith('.broquer-staging.pages.dev'):
    raise SystemExit('Only the named staging Pages project is allowed.')
manifest=json.loads(Path('preview-public-manifest.json').read_text())

def check(pair):
    name,expected=pair
    url=args.origin.rstrip('/')+'/'+quote(name,safe='/')
    try:
        with tempfile.TemporaryDirectory() as tmp:
            payload=Path(tmp)/'body'; header=Path(tmp)/'headers'
            command=['curl','-sS','--max-time','35','-D',str(header),'-o',str(payload),'-w','%{http_code}',url]
            r=subprocess.run(command,capture_output=True,text=True)
            if r.returncode: return {'path':name,'error':'curl_transport','exit_code':r.returncode}
            body=payload.read_bytes(); status=int(r.stdout); headers=header.read_text().lower()
        return {'path':name,'status':status,'matches_manifest':hashlib.sha256(body).hexdigest()==expected,'production_reference':any(x in body.lower() for x in [b'api.broquer.app',b'urtgysmtnvoqaljuhntz']),'staging_header':'x-cecil-preview: staging-only' in headers}
    except Exception as exc:
        return {'path':name,'status':getattr(exc,'code',None),'error':type(exc).__name__}

files=[item for item in manifest.items() if item[0]!='_headers']
results=[]
with ThreadPoolExecutor(max_workers=12) as pool:
    futures=[pool.submit(check,item) for item in files]
    for future in as_completed(futures):
        results.append(future.result())
        if len(results)%40==0:print(f'Checked {len(results)}/{len(files)} files',flush=True)
passed=all(r.get('status')==200 and r.get('matches_manifest') and r.get('staging_header') and not r.get('production_reference') for r in results)
report={'at_utc':datetime.now(timezone.utc).isoformat(),'origin':args.origin,'passed':passed,'count':len(results),'note':'_headers is a Cloudflare control file, scanned locally; not an HTTP asset. This audit does not execute authenticated app flows.','files':sorted(results,key=lambda r:r['path'])}
Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='files'}))
if not passed:raise SystemExit(1)
