"""Explicit, staging-only connected checks. Credentials stay outside git.
Run manually, never during unit discovery. No production host is accepted.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlsplit
from datetime import datetime, timezone
import uuid

API='https://brokr-main-staging.up.railway.app'
DB='https://tymhlvawnqadqgwnpruk.supabase.co'
KEY='sb_publishable_oXqQTLbZh012xaO_6IRUcA_e6-C0fwi'
ORIGIN='https://work-cecil-staging-preview-2.broquer-staging.pages.dev'
PRIVATE=Path('/workspace/scratch/aff5e615a76d/staging-private/accounts-v2.json')
REPORT=Path('docs/staging/connected-tests-20261119.json')


def request(method,url,body=None,token=None,extra=None,binary=None,timeout=50):
    if urlsplit(url).scheme!='https' or urlsplit(url).netloc not in {urlsplit(API).netloc,urlsplit(DB).netloc}:
        raise ValueError('Only isolated staging API/database are permitted')
    headers={'Origin':ORIGIN}
    if url.startswith(DB):headers['apikey']=KEY
    if token:headers['Authorization']='Bearer '+token
    if binary is None:headers['Content-Type']='application/json'
    headers.update(extra or {})
    with tempfile.TemporaryDirectory() as temp:
        cfg=Path(temp)/'curl.cfg';cfg.write_text('\n'.join('header = '+json.dumps(k+': '+v) for k,v in headers.items()));os.chmod(cfg,0o600)
        cmd=['curl','-sS','--max-time',str(timeout),'--config',str(cfg),'-X',method,'-w','\n%{http_code}',url]
        data=binary if binary is not None else json.dumps(body).encode() if body is not None else None
        if data is not None:cmd+=['--data-binary','@-']
        res=subprocess.run(cmd,input=data,capture_output=True)
        if res.returncode: return 0,{'transport_error':res.returncode},b''
        payload,status=res.stdout.rsplit(b'\n',1)
        try: parsed=json.loads(payload)
        except (ValueError,UnicodeDecodeError):parsed=None
        return int(status),parsed,payload


def actors():
    accounts=json.loads(PRIVATE.read_text())
    for label,item in accounts.items():
        status,d,_=request('POST',DB+'/auth/v1/token?grant_type=password',{'email':item['email'],'password':item['password']})
        if status!=200 or not d.get('access_token'):raise RuntimeError('Staging authentication failed for '+label+' status='+str(status))
        item.update(access_token=d['access_token'],refresh_token=d.get('refresh_token'),user_id=d['user']['id'],state='authenticated')
    PRIVATE.write_text(json.dumps(accounts));os.chmod(PRIVATE,0o600)
    return accounts


def record(report,name,status,passed,details=None):
    report['checks'].append({'name':name,'http_status':status,'passed':bool(passed),'details':details})
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(name,status,'OK' if passed else 'FAIL',flush=True)


def main():
    report={'at_utc':datetime.now(timezone.utc).isoformat(),'api':API,'database_ref':urlsplit(DB).hostname.split('.')[0],'checks':[]}
    accounts=actors()
    for label,item in accounts.items():
        status,rows,_=request('GET',DB+'/rest/v1/usuarios?id=eq.'+item['user_id']+'&select=id,plan,nombre',token=item['access_token'])
        record(report,'auth_profile_'+label,status,status==200 and bool(rows),{'profile':rows if status==200 else rows})
    status,schema,_=request('GET',API+'/openapi.json')
    if status==200:Path('/tmp/cecil-staging-openapi.json').write_text(json.dumps(schema))
    record(report,'staging_openapi',status,status==200)

if __name__=='__main__':main()
