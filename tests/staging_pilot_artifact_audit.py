"""Explicit HTTP artifact audit. Cookies stay private; never a browser session."""
import concurrent.futures,hashlib,json
from pathlib import Path
import staging_connected_probe as p

p.API='https://work-cecil-staging-preview-2.broquer-staging.pages.dev'
a=json.loads(Path('/workspace/scratch/aff5e615a76d/staging-private/accounts-v3.json').read_text())['A3']
manifest=json.loads(Path('preview-public-manifest.json').read_text())
entries=[(name,sha) for name,sha in manifest.items() if name!='_headers']
def check(item):
 name,expected=item
 status,_,body=p.request('GET',p.API+'/'+name,extra={'Cookie':'cecil_staging_session='+a['access_token']},timeout=45)
 digest=hashlib.sha256(body).hexdigest()
 return {'path':name,'status':status,'hash_matches':digest==expected,'no_production_reference':all(x not in body.lower() for x in (b'api.broquer.app',b'urtgysmtnvoqaljuhntz'))}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:rows=list(pool.map(check,entries))
passed=all(r['status']==200 and r['hash_matches'] and r['no_production_reference'] for r in rows)
report={'mode':'HTTP audit with private A3 cookie, no browser state injection','passed':passed,'checked':len(rows),'checks':rows}
Path('docs/staging/published-pilot-files-live-20261121.json').write_text(json.dumps(report,indent=2)+'\n')
print('Live artifact audit:',len(rows),'files,','PASS' if passed else 'FAIL')
if not passed:print([r['path'] for r in rows if r['status']!=200 or not r['hash_matches'] or not r['no_production_reference']])
