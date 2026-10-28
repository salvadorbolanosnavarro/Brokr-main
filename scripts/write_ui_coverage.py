"""Build honest per-page and per-endpoint coverage from browser evidence."""
from pathlib import Path
import json,re,copy
ROOT=Path(__file__).resolve().parents[1]
report=json.loads((ROOT/'test-results/ui-application/report.json').read_text())
inv=json.loads((ROOT/'redesign-inventory.json').read_text())
crm=json.loads((ROOT/'test-results/crm/report.json').read_text())
flows=json.loads((ROOT/'test-results/ui-workflows/report.json').read_text())
demo=json.loads((ROOT/'test-results/demo/report.json').read_text())
output=ROOT/'docs/redesign';output.mkdir(exist_ok=True)
# Preserve measured values and source hashes; omit long repeated selector lists.
compact=copy.deepcopy(report)
for row in compact['results']:
 row['fontSizes']={key:[]for key in row.get('fontSizes',{})}
 row['buttons']=[b for b in row.get('buttons',[])if b.get('kind')in {'primary','secondary','text','danger'}]
(output/'ui-application-20261028.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2)+'\n')
countries=json.loads((ROOT/'test-results/countries/report.json').read_text());(output/'country-ui-20261028.json').write_text(json.dumps(countries,ensure_ascii=False,indent=2)+'\n')
(output/'ui-workflows-20261028.json').write_text(json.dumps(flows,ensure_ascii=False,indent=2)+'\n')
(output/'crm-states-20261028.json').write_text(json.dumps(crm,ensure_ascii=False,indent=2)+'\n')
calls=[]
for row in report['results']:
 for call in row.get('calls',[]):
  if call.get('status')and 200<=call['status']<300:calls.append((call['method'],re.sub(r'^/api(?=/)','',call['path'])))
for row in crm['results']:
 if row['passed']and row['scenario']=='data':
  for call in row.get('calls',[]):calls.append((call['method'],call['path']))
rows={}
for row in report['results']:rows.setdefault(row['page'],{})[row['width']]=row
interactive={'contactos.html','clientes.html','propiedades.html','tareas.html','finanzas.html','crm-ajustes.html','buzon.html','alertas.html'}
lines=['# Cobertura de la migración UI — 28 de octubre de 2026','',
f'Base de rutas: main `{inv["baseline"]}` integrado en esta rama ({len(inv["routes"])} operaciones HTTP). No hay IDs de controles retirados respecto a esa base. Nada se ha fusionado a main.','',
'**Rediseñado** indica componentes compartidos aplicados; **probado con mock** indica evidencia de navegador/fixtures; **probado real** exige backend y base aislados. Cero pruebas reales se atribuyen a esta entrega. Un HTTP 501 de una integración desactivada queda pendiente, nunca aprobado.','',
'## Pantallas','',
f'{len(rows)-7} páginas principales + 2 callbacks OAuth + 5 páginas de referencia = {len(rows)} ejecutables; {len(report["results"])} vistas a 1440/390 px. Se incluye Impuestos por venta, añadido en el main actual. Los archivos que empiezan con guion bajo son plantillas.','',
'Las pruebas generales verifican superficie, acciones, fuentes, fechas, superposición, montos y errores JavaScript. Guardado/recarga y flujos solo se atribuyen a las pantallas expresamente probadas. Los callbacks no prueban una conexión OAuth real.','',
'| Pantalla | UI | Mock 1440 / 390 | Real | Alcance adicional |','|---|---|---|---|---|']
for path in sorted(rows):
 views=rows[path];ok=all(w in views and not any(views[w].get(k)for k in ['failure','errors','overflow','smallFields','overlaps','clippedKpis'])for w in [1440,390])
 extra='Superficie'
 if path in interactive:extra='Flujo o estados/rol; ver evidencia JSON'
 if 'callback' in path:extra='Navegación de callback; OAuth pendiente'
 if path.startswith('preview-modo/')or path.startswith('videos/'):extra='Referencia suplementaria'
 lines.append(f'| `{path}` | Rediseñado | {"Probado con mock"if ok else"Pendiente"} | Pendiente | {extra} |')
lines+=['','## Endpoints HTTP','','Cada fila corresponde a una operación del contrato inventariado. "Probado con mock" aquí significa invocado y respondido en una simulación; no demuestra su persistencia, autorización real, efectos externos o contrato completo.','',
'| Método | Endpoint | Estado |','|---|---|---|']
mock=0
for route in inv['routes']:
 pattern='^'+re.sub(r'\\\{[^}]+\\\}',r'[^/]+',re.escape(route['path']))+'$'
 hit=any(method==route['method']and re.fullmatch(pattern,path)for method,path in calls)
 if hit:mock+=1
 lines.append(f'| {route["method"]} | `{route["path"]}` | {"Probado con mock"if hit else"Pendiente"} |')
lines+=['',f'HTTP: {mock} operaciones invocadas con mock; {len(inv["routes"])-mock} pendientes. Ninguna probada real.','',
'## Cierre de pruebas reales','',
'La demo guarda datos ficticios en el navegador. El backend Railway y Cloudflare existentes siguen siendo los únicos destinos de staging. Las comprobaciones reales de guardado, RLS, funciones, triggers y storage esperan el esquema completo y una base Supabase aislada con su configuración en Railway; no se usa producción ni broquer-beta. Los pasos de configuración están en `STAGING_SETUP.md`. Stripe continúa en test para el entorno conectado; WhatsApp/Meta, push y correos no se envían desde la demo.','',
'La emulación Chromium a 390 px no sustituye una prueba de WKWebView en un iPhone real. El suelo de 16 px y los cambios de viewport se conservan en el código; la comprobación nativa queda pendiente.','',
'La suite histórica completa no se declara aprobada por estos resultados: esta entrega certifica los controles de UI y los flujos mock enumerados. La suite y los límites de arquitectura previos deben revisarse antes de pedir aprobación de merge.']
(output/'COBERTURA-UI-Y-ENDPOINTS.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'pages':len(rows),'views':len(report['results']),'crm_passed':sum(r['passed']for r in crm['results']),'crm_cases':len(crm['results']),'http_mock':mock,'http_pending':len(inv['routes'])-mock,'real':0}))
