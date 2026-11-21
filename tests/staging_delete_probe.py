import sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import staging_connected_probe as p
p.REPORT=Path('docs/staging/delete-tests-20261119.json')
report={'mode':'real staging API; only disposable QA records','checks':[]}
a=json.loads(p.PRIVATE.read_text());state=json.loads(Path('/workspace/scratch/aff5e615a76d/staging-private/qa-records.json').read_text())
for kind,table in [('contacts','contactos'),('leads','contactos'),('properties','propiedades')]:
 for label,other in [('A','B'),('B','A')]:
  if other not in state[kind]:continue
  rid=state[kind][other]['id'];owner=a[other];actor=a[label]
  st,d,_=p.request('POST',p.API+'/'+table+'/eliminar-masivo',{'ids':[rid]},token=actor['access_token'])
  verify,rows,_=p.request('GET',p.DB+'/rest/v1/'+table+'?id=eq.'+rid+'&select=id',token=owner['access_token'])
  p.record(report,'cannot_delete_other_'+kind+'_'+label,st,verify==200 and bool(rows),{'owner_record_still_exists':bool(rows),'response':d})
 for label,actor in a.items():
  if label not in state[kind]:continue
  rid=state[kind][label]['id']
  st,d,_=p.request('POST',p.API+'/'+table+'/eliminar-masivo',{'ids':[rid]},token=actor['access_token'])
  verify,rows,_=p.request('GET',p.DB+'/rest/v1/'+table+'?id=eq.'+rid+'&select=id',token=actor['access_token'])
  p.record(report,'delete_own_'+kind+'_'+label,st,st==200 and verify==200 and rows==[],{'record_absent':rows==[],'response':d})
