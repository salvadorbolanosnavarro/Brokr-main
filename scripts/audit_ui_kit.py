"""Enforce the proposed component contract without exempting legacy modules.

Scope is the approval showroom and its shared CSS. The existing application
is deliberately not declared migrated; that audit expands after approval.
"""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
def inspect(html,css,tokens):
    errors=[]
    if re.search(r'\sstyle\s*=',html,re.I) or '<style' in html.lower():errors.append('Inline/module CSS is forbidden in the showroom')
    sizes=re.findall(r'--ui-text-[\w-]+\s*:\s*(\d+)px',tokens)
    if len(sizes)!=7 or sorted(map(int,sizes))!=[12,14,16,20,24,32,48]:errors.append('Typography must use the seven approved sizes')
    for prop,value in re.findall(r'(?<![\w-])(font-size|color|background(?:-color)?|border-radius)\s*:\s*([^;}]+)',css):
        if not ('var(--ui-' in value or value.strip() in {'inherit','transparent','none','0'}):errors.append(f'Non-token {prop}: {value}')
    if re.search(r'font-family\s*:[^;}]*Inter',css+tokens,re.I):errors.append('Inter is not part of this system')
    for key in ['buttons','fields','filters','navigation','cards','overlays','modal-sample','account-sample','broq-sample','calendar-sample']:
        if f'id="{key}"' not in html:errors.append('Missing component: '+key)
    for name,expected in [('control','48px'),('control-small','44px'),('radius','12px')]:
        if not re.search(r'--ui-'+name+r'\s*:\s*'+expected,tokens):errors.append('Invalid '+name)
    return errors
if __name__=='__main__':
    errors=inspect((ROOT/'ui-components.html').read_text(),(ROOT/'ui/components.css').read_text(),(ROOT/'ui/tokens.css').read_text())
    for error in errors:print(error)
    print(f'UI component contract: {len(errors)} violations (approval showroom only)')
    raise SystemExit(bool(errors))
