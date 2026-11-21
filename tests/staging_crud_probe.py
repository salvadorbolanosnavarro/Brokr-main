import sys,json,uuid
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from staging_connected_probe import *
accounts=json.loads(PRIVATE.read_text());report=json.loads(REPORT.read_text())
state={'properties':{},'contacts':{},'leads':{}}
P=Path('/workspace/scratch/aff5e615a76d/staging-private/qa-records.json')
if P.exists():state=json.loads(P.read_text())

def save():P.write_text(json.dumps(state));os.chmod(P,0o600)
def detail(d):return {k:d.get(k) for k in ('code','message','detail') if isinstance(d,dict) and k in d}
for kind,table in [('properties','propiedades'),('contacts','contactos'),('leads','contactos')]:
 for label,a in accounts.items():
  if label in state[kind]:continue
  marker='QA_CECIL_'+label+'2_'+kind
  if kind=='properties': body={'user_id':a['user_id'],'titulo':marker,'tipo':'casa','operacion':'venta','precio':2500000,'moneda':'MXN','estatus':'activa','ciudad':'Morelia','estado':'Michoacán','colonia':'Colonia ficticia QA','descripcion':'Datos ficticios de pruebas. No publicar.','fotos':[],'en_bolsa':False}
  else:body={'id':'c_qa_'+uuid.uuid4().hex[:16],'user_id':a['user_id'],'nombre':marker,'telefono':'0000000000','tipo':'comprador','es_potencial':kind=='leads','estatus':'nuevo'}
  st,d,_=request('POST',DB+'/rest/v1/'+table,body,token=a['access_token'],extra={'Prefer':'return=representation'})
  ok=st in (200,201) and isinstance(d,list) and len(d)==1
  record(report,'create_'+kind+'_'+label,st,ok,{'id':d[0]['id']} if ok else detail(d))
  if ok:state[kind][label]={'id':d[0]['id'],'marker':marker};save()
 # Strong negative checks only use disposable records created above.
 for label,other in [('A','B'),('B','A')]:
  if other not in state[kind]:continue
  a=accounts[label];rid=state[kind][other]['id']
  st,d,_=request('GET',DB+'/rest/v1/'+table+'?id=eq.'+rid+'&select=id',token=a['access_token'])
  record(report,'cannot_read_other_'+kind+'_'+label,st,st==200 and d==[],{'rows':len(d) if isinstance(d,list) else None})
  path='/propiedades/'+rid if kind=='properties' else '/org/contactos/'+rid
  body={'titulo':'UNAUTHORIZED_QA'} if kind=='properties' else {'nombre':'UNAUTHORIZED_QA'}
  st,d,_=request('PATCH',API+path,body,token=a['access_token'])
  record(report,'cannot_edit_other_'+kind+'_'+label,st,st in (403,404),detail(d))
 for label,a in accounts.items():
  if label not in state[kind]:continue
  item=state[kind][label];rid=item['id'];new=item['marker']+'_EDITED'
  path='/propiedades/'+rid if kind=='properties' else '/org/contactos/'+rid
  body={'titulo':new} if kind=='properties' else {'nombre':new}
  st,d,_=request('PATCH',API+path,body,token=a['access_token'])
  record(report,'edit_'+kind+'_'+label,st,st==200,detail(d))
  col='titulo' if kind=='properties' else 'nombre'
  st,d,_=request('GET',DB+'/rest/v1/'+table+'?id=eq.'+rid+'&select=id,'+col,token=a['access_token'])
  record(report,'verify_edit_'+kind+'_'+label,st,st==200 and bool(d) and d[0].get(col)==new)
save()
