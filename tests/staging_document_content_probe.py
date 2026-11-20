import sys,json,zipfile,io
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import staging_connected_probe as p
p.REPORT=Path('docs/staging/document-download-tests-20261119.json');r={'checks':[]}
d=json.loads(Path('/workspace/scratch/aff5e615a76d/staging-private/generate_ficha-response.json').read_text())
s,_,b=p.request('GET',p.API+'/ficha-pdf/'+d['token'])
Path('docs/staging/QA-A2-ficha.pdf').write_bytes(b)
valid=b.startswith(b'%PDF') and b'%%EOF' in b[-2048:]
if valid:
 import subprocess
 text=subprocess.run(['pdftotext','docs/staging/QA-A2-ficha.pdf','-'],capture_output=True,text=True).stdout
 valid='QA CECIL A2 CASA FICTICIA' in text
p.record(r,'ficha_download_content',s,s==200 and valid,{'bytes':len(b),'contains_fictitious_title':bool(valid)})
f=Path('docs/staging/QA-A2-contract.docx')
z=zipfile.ZipFile(io.BytesIO(f.read_bytes()));xml=z.read('word/document.xml').decode()
p.record(r,'contract_docx_content',200,'ARRENDADOR FICTICIO QA' in xml and 'ARRENDATARIO FICTICIO QA' in xml,{'bytes':f.stat().st_size,'contains_fictitious_parties':'ARRENDATARIO FICTICIO QA' in xml})
