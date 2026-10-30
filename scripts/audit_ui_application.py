"""Strict audit of measured rendered UI; never substitutes for live workflow QA.

Run measure_ui_application.cjs first. Source hashes prevent stale evidence from
passing after an HTML/CSS/JS change. Structural list/media buttons and tabs have
separate contracts; normal action buttons must use the approved component.
"""
from pathlib import Path
import hashlib,json,sys,os
ROOT=Path(__file__).resolve().parents[1]
def inspect(report):
 errors=[];scale={'12px','14px','16px','20px','24px','32px','48px'};combinations=set()
 for name,digest in report.get('hashes',{}).items():
  p=ROOT/name
  if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:errors.append(f'Stale measurement: {name}')
 if not report.get('hashes'):errors.append('Missing source hashes')
 results=report.get('results',[])
 expected={p['path'] for p in json.loads((ROOT/'redesign-inventory.json').read_text())['pages'] if not p['path'].startswith('_')}
 if {(r['page'],r['width'])for r in results}!={(p,w)for p in expected for w in (1440,390)}:errors.append('Every executable baseline page must be measured at 1440/390')
 card_titles={'404.html','sitio.html','expediente.html','firmar.html','unirse.html','verificar-firma.html'}
 for r in results:
  label=f"{r['page']}:{r['width']}"
  if r.get('failure') or r.get('errors') or r.get('overflow') or r.get('smallFields') or r.get('overlaps') or r.get('clippedKpis'):errors.append(label+': surface failure')
  if set(r.get('fontSizes',{}))-scale:errors.append(label+': non-approved text size')
  if r.get('dateFields')!=r.get('spanishDates'):errors.append(label+': date field missing Spanish proxy')
  if '/'not in r['page'] and not r['title'].endswith(' · ' + os.environ.get('BROQUER_TEST_BRAND', 'Broquer')):errors.append(label+': title format')
  if '/'not in r['page'] and r['page']not in card_titles and r.get('h1') and r['h1']['size']!=('32px'if r['width']==390 else'48px'):errors.append(label+': module H1 scale')
  for b in r.get('buttons',[]):
   if b.get('kind')not in {'primary','secondary','text','danger'}:continue
   if (b['height'],b['font'],b['radius'],b['weight'])not in {(h,'14px','12px','600')for h in (44,48)}:errors.append(label+': action geometry '+str(b.get('id')or b.get('class')))
   combinations.add((b['height'],b['background'],b['color']))
 if len(combinations)>10:errors.append(f'Action variants exceed 5 × 2: {len(combinations)}')
 return errors,len(combinations)
if __name__=='__main__':
 path=Path(sys.argv[1])if len(sys.argv)>1 else ROOT/'test-results/ui-application/report.json'
 if not path.exists():raise SystemExit('Measure the application before auditing it.')
 errors,count=inspect(json.loads(path.read_text()))
 for error in errors:print(error)
 print(f'Rendered UI: {len(errors)} violations; {count} observed action variants/sizes')
 raise SystemExit(bool(errors))
