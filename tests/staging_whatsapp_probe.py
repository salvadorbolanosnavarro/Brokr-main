import sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import staging_connected_probe as p
p.REPORT=Path('docs/staging/whatsapp-simulated-20261119.json')
a=json.loads(p.PRIVATE.read_text())['A']; report={'api':p.API,'account':'A2','checks':[]}
s,d,_=p.request('POST',p.API+'/whatsapp-chatgpt/send-test',{'phone_number_id':'QA_CECIL_A2_NOT_A_META_ID','to':'0000000000','body':'PRUEBA QA STAGING. No entregar.'},token=a['access_token'])
p.record(report,'authenticated_whatsapp_send_test',s,s in (200,409) and isinstance(d,dict) and d.get('simulated') is True and d.get('external_call_performed') is False,d)
