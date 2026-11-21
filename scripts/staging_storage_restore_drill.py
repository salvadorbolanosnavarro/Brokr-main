"""Explicit staging-only Storage recovery drill. Never runs in test discovery.
Creates its own disposable photo; never deletes any pre-existing object.
Credentials are read from a private account file outside Git.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import uuid
from datetime import datetime, timezone
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import staging_connected_probe as p


def run(private, report):
    p.PRIVATE=Path(private)
    a=p.actors()['A3']; token=a['access_token']
    bucket='fotos-propiedades';run_id=uuid.uuid4().hex
    source=f"{a['user_id']}/qa-storage-{run_id}.jpg"
    backup=f"{a['user_id']}/qa-storage-backup-{run_id}/photo.jpg"
    image=Image.new('RGB',(640,400),'#f4f0e8');d=ImageDraw.Draw(image)
    d.rectangle((160,150,480,350),fill='#ff781f');d.polygon([(120,150),(320,30),(520,150)],fill='#20262c')
    d.text((20,375),'QA CECIL - FOTO FICTICIA - RESTORE STAGING',fill='#20262c')
    out=io.BytesIO();image.save(out,'JPEG',quality=88);payload=out.getvalue()
    digest=hashlib.sha256(payload).hexdigest();checks=[];started=time.monotonic()
    def req(method,path,body=None,binary=None):
        return p.request(method,p.DB+'/storage/v1/'+path,body,token=token,binary=binary,
                         extra={'Content-Type':'image/jpeg'} if binary is not None else None)
    def check(name,passed,status,**details):
        checks.append({'name':name,'passed':passed,'http_status':status,**details})
        Path(report).parent.mkdir(parents=True,exist_ok=True)
        Path(report).write_text(json.dumps({'project_ref':'tymhlvawnqadqgwnpruk','at_utc':datetime.now(timezone.utc).isoformat(),'bucket':bucket,'source':source,'backup':backup,'bytes':len(payload),'sha256':digest,'checks':checks,'seconds':round(time.monotonic()-started,3)},indent=2)+'\n')
        if not passed:raise RuntimeError('Storage drill failed: '+name+' status='+str(status))
    def download(path):
        return req('GET',f'object/authenticated/{bucket}/{path}?qa={uuid.uuid4().hex}')
    s,_,_=req('POST',f'object/{bucket}/{source}',binary=payload);check('upload_own_new_fixture',s in (200,201),s)
    begin=time.monotonic()
    s,_,_=req('POST','object/copy',{'bucketId':bucket,'sourceKey':source,'destinationKey':backup});check('copy_to_backup_folder',s in (200,201),s,seconds=round(time.monotonic()-begin,3))
    s,_,raw=download(backup);check('backup_sha256_verified',s==200 and hashlib.sha256(raw).hexdigest()==digest,s)
    s,_,_=req('DELETE',f'object/{bucket}',{'prefixes':[source]});check('delete_only_own_fixture',s in (200,204),s)
    s,_,_=download(source);check('deleted_fixture_missing',s in (400,404),s)
    begin=time.monotonic()
    s,_,_=req('POST','object/copy',{'bucketId':bucket,'sourceKey':backup,'destinationKey':source});check('restore_same_original_key',s in (200,201),s,seconds=round(time.monotonic()-begin,3))
    s,_,raw=download(source);check('restored_sha256_identical',s==200 and len(raw)==len(payload) and hashlib.sha256(raw).hexdigest()==digest,s)
    print(json.dumps({'passed':True,'checks':len(checks),'seconds':round(time.monotonic()-started,3),'sha256':digest,'bytes':len(payload)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--private',required=True);parser.add_argument('--report',required=True)
    a=parser.parse_args();run(a.private,a.report)
