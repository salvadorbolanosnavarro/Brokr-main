"""Inventory all tracked HTML and backend routes against the migration baseline.
Static evidence only: presence of source does not prove runtime behavior.
"""
import ast
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '1f5fc8d5a5a7650bd315bfead3515d708f828bae'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True)
class Page(HTMLParser):
    def __init__(self, source):
        super().__init__(); self.ids=set(); self.controls=[]; self.links=set(); self.scripts=[]; self.app=None
        self.feed(source)
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if a.get('id'): self.ids.add(a['id'])
        if tag=='body': self.app=a.get('data-app')
        if tag in ('input','select','textarea','button','form'):
            self.controls.append({'tag':tag, **{k:a[k] for k in ('id','name','type','onclick','onsubmit') if k in a}})
        if tag=='a' and a.get('href'): self.links.add(a['href'])
        if tag=='script' and a.get('src'): self.scripts.append(a['src'])

files=git('ls-tree','-r','--name-only',BASE).splitlines()
pages=[]
for name in files:
    if not name.endswith('.html'): continue
    old=git('show',BASE+':'+name); path=ROOT/name
    new=path.read_text() if path.exists() else ''
    before,after=Page(old),Page(new)
    pages.append({'path':name,'exists':path.exists(),'app':after.app,
        'shared_shell':'app-shell.js' in after.scripts and name not in {'login.html','registro.html','ficha-pdf-preview.html','legal.html','admin.html'},
        'shared_theme':'brokr-theme.css' in new,
        'source_unchanged':old==new,'controls':after.controls,
        'removed_control_ids':sorted({c['id'] for c in before.controls if c.get('id')} - after.ids),
        'removed_ids':sorted(before.ids-after.ids),
        'links':sorted(after.links),'scripts':after.scripts,
        'runtime_status':'not-certified'})
routes=[]
for name in files:
    if not name.endswith('.py') or not (name.startswith('routers/') or name=='main.py'): continue
    tree=ast.parse((ROOT/name).read_text())
    prefixes={}
    for item in ast.walk(tree):
        if isinstance(item,ast.Assign) and isinstance(item.value,ast.Call) and getattr(item.value.func,'id',None)=='APIRouter':
            prefix=next((k.value.value for k in item.value.keywords if k.arg=='prefix' and isinstance(k.value,ast.Constant)), '')
            for target in item.targets:
                if isinstance(target,ast.Name): prefixes[target.id]=prefix
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): continue
        for d in node.decorator_list:
            if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr in ('get','post','put','patch','delete','websocket') and d.args:
                routes.append({'file':name,'handler':node.name,'method':d.func.attr.upper(),'path_expression':ast.unparse(d.args[0]),'path':prefixes.get(getattr(d.func.value,'id',''),'') + (d.args[0].value if isinstance(d.args[0],ast.Constant) else ast.unparse(d.args[0]))})
declared_routes=routes
golden=json.loads((ROOT/'tests/golden/http_contract_effective.json').read_text())
routes=[{'method':r['method'],'path':r['path'],'file':'Contrato HTTP efectivo actual','handler':'registro de main','path_expression':repr(r['path'])} for r in golden['operations']]
changed=git('diff','--name-only',BASE,'--','core','routers','main.py','tests').splitlines()
report={'baseline':BASE,'pages':pages,'routes':routes,'route_declarations':declared_routes,'changed_backend_or_existing_tests':changed,
    'warning':'Static inventory, not a certification of functional or visual parity. Endpoint table uses the effective HTTP golden contract from the current main baseline; runtime comparison remains pending.'}
(ROOT/'redesign-inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
lines=['# Cobertura completa de Broquer','',
 'Las ocho referencias definen el lenguaje visual; todas las pantallas y flujos originales forman parte de la migración.', '',
 f'Inventario reproducible: `{BASE}`. {len(pages)} HTML rastreados y {len(routes)} operaciones del contrato HTTP efectivo actual (se conserva también el inventario de declaraciones).',
 'La presencia del código no certifica su funcionamiento. Todos los flujos requieren validación con servicios de pruebas.', '',
 '| Pantalla | Rediseño | Mock | Prueba real | Datos / vacío / error / carga | Roles | Móvil iPhone real | IDs retirados |',
 '| --- | --- | --- | --- | --- | --- | --- | --- |']
mock_results=[]
for filename in ('report.json','focused-report.json'):
    report_path=ROOT/'test-results/modules'/filename
    if report_path.exists(): mock_results+=json.loads(report_path.read_text()).get('results',[])
for p in pages:
    runs=[r for r in mock_results if r.get('page')==p['path']]
    latest={r['width']:r for r in runs}
    passed=len(latest)>=2 and all(not r.get('failure') and not r.get('overflow') and not r.get('errors') for r in latest.values())
    redesign='Rediseñado; fidelidad pendiente' if p['shared_shell'] or p['path'] in {'login.html','registro.html','reset-password.html','unirse.html','firmar.html','verificar-firma.html','expediente.html'} else 'Pendiente de revisión visual'
    lines.append(f"| `{p['path']}` | {redesign} | {'Probado con mock: superficie en versión previa' if passed else 'Pendiente'} | Pendiente | Pendiente de flujos completos | Pendiente de matriz completa | Pendiente | {', '.join(p['removed_control_ids']) or 'Ninguno'} |")
lines += ['', '## Cada endpoint', '', 'Estas filas enumeran cada operación del contrato HTTP efectivo de main. El JSON conserva además cada declaración con su handler. El mock de la interfaz no demuestra que un endpoint funcione. Las integraciones externas se bloquearán en staging y se validarán por separado.', '', '| Método | Ruta declarada con prefijo local | Fuente / handler | Mock endpoint | Prueba real |', '| --- | --- | --- | --- | --- |']
for route in routes:
    lines.append(f"| {route['method']} | `{route['path']}` | `{route['file']}: {route['handler']}` | Pendiente | Pendiente |")
lines+=['','## Criterios de cobertura','',
 '- CRM: altas, edición, filtros, etapas, importación/exportación, archivos y permisos.',
 '- Documentos: contratos, firma, verificación pública, expediente, cumplimiento y descargas.',
 '- Finanzas: cuentas, movimientos, reportes, estimación de valor e ISR.',
 '- Comunicación: WhatsApp, números, chats, recepción automática, correo y notificaciones.',
 '- Marketing: fotografías, fichas, video, campañas, sitio público y configuración del agente.',
 '- Cuenta: registro, acceso, recuperación, invitaciones, equipo, roles, suscripción y administración.',
 '- Transversal: Broq, móvil/iOS, navegación, badges, errores, cargas, estados vacíos y accesibilidad.',
 '- Páginas públicas y callbacks: conservar contratos de URL, tokens y redirecciones.', '',
 'Los módulos ocultos o desactivados mantienen las reglas originales; conservar su código no implica habilitarlos.',
 'Los detalles de controles y rutas se encuentran en `redesign-inventory.json`.',
 'Actualizar con `python scripts/inventory_redesign.py`.']
(ROOT/'REDESIGN_COVERAGE.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'pages':len(pages),'routes':len(routes),'changed_backend_or_existing_tests':changed,'removed_controls':{p['path']:p['removed_control_ids'] for p in pages if p['removed_control_ids']}},ensure_ascii=False))
