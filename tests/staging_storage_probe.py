import sys,json,uuid
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import staging_connected_probe as p
p.REPORT=Path('docs/staging/whatsapp-storage-tests-20261119.json')
report={'mode':'staging A2/B2, invalid synthetic WhatsApp connection only','checks':[]}
a=json.loads(p.PRIVATE.read_text());owner=a['A'];token=owner['access_token']
# Authenticated requests to the real WhatsApp sending endpoint. No valid Meta
# number or credential is used, so this fixture cannot deliver any message.
fake_id='QA_FAKE_'+uuid.uuid4().hex[:12]
body={'user_id':owner['user_id'],'waba_id':'QA_FAKE_WABA','phone_number_id':fake_id,'access_token':'QA_FAKE_INVALID_META_TOKEN','display_number':'0000000000','ai_enabled':False,'identity_prompt':'QA, no enviar mensajes reales.'}
st,d,_=p.request('POST',p.DB+'/rest/v1/wac_numbers',body,token=token,extra={'Prefer':'return=representation'})
inserted=st==201
p.record(report,'seed_fake_whatsapp_connection',st,inserted,{'code':d.get('code'),'message':d.get('message')} if isinstance(d,dict) else {'inserted':inserted})
st,d,_=p.request('POST',p.API+'/whatsapp-chatgpt/send-test',{'phone_number_id':fake_id,'to':'0000000000','body':'PRUEBA QA STAGING. No entregar.'},token=token)
p.record(report,'whatsapp_send_A2_real_endpoint',st,st in (409,503) and isinstance(d,dict) and d.get('external_call_performed') is False and d.get('simulated') is True,d)
if inserted:p.request('DELETE',p.DB+'/rest/v1/wac_numbers?phone_number_id=eq.'+fake_id,token=token)
# Use the same public bucket and MIME as the real photo uploader.
name='qa_cecil_'+uuid.uuid4().hex+'.jpg';payload=Path('/workspace/shared/qa-property-photo.jpg').read_bytes()
st,d,_=p.request('POST',p.DB+'/storage/v1/object/fotos-propiedades/'+name,token=token,extra={'Content-Type':'image/jpeg'},binary=payload)
p.record(report,'photo_upload_A2',st,st in (200,201),{'bytes':len(payload),'object':name,'error':d if st not in (200,201) else None})
if st in (200,201):
 verify,_,raw=p.request('GET',p.DB+'/storage/v1/object/public/fotos-propiedades/'+name)
 p.record(report,'photo_read_uploaded_A2',verify,verify==200 and raw==payload,{'bytes':len(raw)})
 st,d,_=p.request('DELETE',p.DB+'/storage/v1/object/fotos-propiedades',{'prefixes':[name]},token=a['B']['access_token'])
 verify,_,_=p.request('GET',p.DB+'/storage/v1/object/public/fotos-propiedades/'+name)
 p.record(report,'photo_cannot_delete_other_B2',st,verify==200,{'still_exists':verify==200})
 st,d,_=p.request('DELETE',p.DB+'/storage/v1/object/fotos-propiedades',{'prefixes':[name]},token=token)
 verify,_,_=p.request('GET',p.DB+'/storage/v1/object/public/fotos-propiedades/'+name)
 p.record(report,'photo_delete_own_A2',st,st in (200,204) and verify!=200,{'read_after_delete':verify})
st,d,_=p.request('GET',p.DB+'/rest/v1/usuarios?id=eq.'+owner['user_id']+'&select=rol,activo,acceso_completo_hasta',token=token)
p.record(report,'paid_access_profile_schema',st,st==200,{'profile':d})
