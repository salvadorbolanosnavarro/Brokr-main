"""Manual server/API checks only. Not a replacement for the UI rehearsal."""
import json
from pathlib import Path
import staging_connected_probe as p

p.API='https://work-cecil-staging-preview-2.broquer-staging.pages.dev'
p.REPORT=Path('docs/staging/pilot-server-live-20261121.json')
report={'mode':'authenticated server HTTP checks; UI still pending','checks':[]}
a3path=Path('/workspace/scratch/aff5e615a76d/staging-private/accounts-v3.json')
a=json.loads(a3path.read_text())['A3']
b=json.loads(p.PRIVATE.read_text())['B']
# Refresh only B2, never recover/touch A2.
s,d,_=p.request('POST',p.DB+'/auth/v1/token?grant_type=password',{'email':b['email'],'password':b['password']})
if s!=200:raise RuntimeError('B2 API authentication failed')
b['access_token']=d['access_token']
for label,actor,expected in [('A3',a,True),('B2',b,False)]:
 s,d,_=p.request('GET',p.API+'/ui/cecil',token=actor['access_token'])
 p.record(report,label+'_server_flag',s,s==200 and d.get('enabled') is expected,{'enabled':d.get('enabled') if isinstance(d,dict) else None})
 s,d,_=p.request('GET',p.API+'/cecil/contactos.html',extra={'Cookie':'cecil_staging_session='+actor['access_token']})
 p.record(report,label+'_alternate_html_server_gate',s,s==(200 if expected else 302),{'expected_status':200 if expected else 302})
s,d,_=p.request('GET',p.API+'/ui/cecil')
p.record(report,'anonymous_flag_rejected',s,s==401)
s,d,_=p.request('POST',p.API+'/__staging/error-probe',{'probe':'controlled-error-v1'},token=b['access_token'])
p.record(report,'B2_error_probe_denied',s,s==403)
s,d,_=p.request('POST',p.API+'/__staging/error-probe',{'probe':'controlled-error-v1'},token=a['access_token'])
p.record(report,'Sentry_ingestion_and_receipt',s,s==200 and d.get('sentry_accepted') is True and d.get('receipt_saved') is True,d)
# Only private token/file handoff between API tests; no browser session injection.
Path('/workspace/scratch/aff5e615a76d/staging-private/pilot-api-actors.json').write_text(json.dumps({'A3':a,'B2':b}))
Path('/workspace/scratch/aff5e615a76d/staging-private/pilot-api-actors.json').chmod(0o600)
