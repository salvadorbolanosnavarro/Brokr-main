import sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import staging_connected_probe as p
p.REPORT=Path('docs/staging/document-tests-20261119.json')
report={'mode':'real staging API with A2, no external messages','checks':[]}
a=json.loads(p.PRIVATE.read_text())['A'];token=a['access_token']
for name,path,body in [
 ('generate_ficha','/ficha-pdf',{'title':'QA CECIL A2 CASA FICTICIA','property_type':'Casa','description':'Ficha de prueba, inmueble ficticio.','operations':[{'type':'sale','amount':2500000,'currency':'MXN'}],'location':{'name':'Colonia ficticia, Morelia'},'bedrooms':3,'bathrooms':2,'construction_size':180,'lot_size':220,'property_images':[]}),
 ('generate_contract','/contrato',{'tipo':'arrendamiento','datos':{'fecha_contrato':'2026-11-19','nombre_arrendador':'ARRENDADOR FICTICIO QA','nombre_arrendatario':'ARRENDATARIO FICTICIO QA','calle_inmueble':'CALLE DE PRUEBA','num_ext_inmueble':'0','colonia_inmueble':'COLONIA FICTICIA','cp_inmueble':'58000','municipio_estado_inmueble':'MORELIA, MICHOACAN','renta_mensual':10000,'deposito_garantia':10000,'dia_pago':5,'fecha_inicio':'2026-12-01','fecha_fin':'2027-11-30'},'clausulas_especiales':[]}),
 ('generate_avm','/api/avm-websearch',{'colonia':'Altozano','tipo_inmueble':'casa','operacion':'venta','m2_construccion':180,'m2_terreno':220,'ciudad':'Morelia','estado':'Michoacán','comentarios':'PRUEBA QA: inmueble ficticio, no datos de clientes.'})]:
 status,d,payload=p.request('POST',p.API+path,body,token=token,timeout=300)
 details={k:d.get(k) for k in ('detail','code','message','token','filename') if isinstance(d,dict) and k in d}
 # Download tokens are capability credentials: retain privately only.
 if isinstance(d,dict) and d.get('token'):
  private=Path('/workspace/scratch/aff5e615a76d/staging-private/'+name+'-response.json');private.write_text(json.dumps(d));private.chmod(0o600);details.pop('token',None)
 if status==200 and payload[:2]==b'PK':
  Path('docs/staging/QA-A2-contract.docx').write_bytes(payload);details={'docx_bytes':len(payload)}
 p.record(report,name,status,status==200,details)
status,schema,_=p.request('GET',p.DB+'/rest/v1/',token=token,extra={'Accept':'application/openapi+json'})
if status==200 and isinstance(schema,dict):
 Path('/tmp/cecil-staging-db-schema.json').write_text(json.dumps(schema))
 print('DB schema available for own staging fixtures',flush=True)
