// Offline parity against the current main source. No production HTTP requests.
// Fixed synthetic INPC/UDIS fixtures make both engines use identical inputs.
const fs=require('node:fs'),vm=require('node:vm'),cp=require('node:child_process'),assert=require('node:assert/strict');
const baseline=cp.execFileSync('git',['show','dac7118c952deeda4f6b9160c05f19b0a42ca8a0:isr.html'],{encoding:'utf8'});
const redesigned=fs.readFileSync('preview-public/isr.html','utf8');
const baseFields={'f-tipo':'terreno','f-venta':'2800000','f-compra':'1350000','f-mes-c':'11','f-anio-c':'2023','f-fecha-v':'2026-10-02','f-mej':'0','f-com':'112000','f-esc':'20000','f-forma-adq':'compra','f-copro':'no','f-pct-terreno':'20','f-pct-const':'80','f-pri':'si','f-exp':'no'};
const cases=[['terreno',{}],['casa exenta',{'f-tipo':'casa','f-venta':'3850000','f-compra':'387352','f-mes-c':'12','f-anio-c':'2009'}],['casa sin exencion',{'f-tipo':'casa','f-venta':'15000000','f-pri':'no'}],['comercial',{'f-tipo':'comercial','f-venta':'12000000','f-compra':'4000000'}],['perdida',{'f-venta':'1000000','f-compra':'3000000'}],['copropiedad',{'f-tipo':'casa','f-venta':'15000000','f-copro':'si','f-pct-copro':'50','f-pri':'no'}]];
async function run(html,fields){
 const elements=new Map();
 const context={console,Date,Math,window:{API_BASE:'https://brokr-main-staging.up.railway.app'},document:{getElementById:id=>{if(!elements.has(id))elements.set(id,{value:String(fields[id]??''),checked:false,disabled:false,innerHTML:'Calcular',style:{},classList:{add(){},remove(){}}});return elements.get(id);}},alert:message=>{throw Error(message);},fetch:async url=>{const parts=url.split('/');const year=Number(parts.at(-2)),month=Number(parts.at(-1));return{ok:true,json:async()=>url.includes('/udis/')?{valor:8.5}:{valor:year>=2024?140+(year-2024)*5:80,anio:year,mes:month,fallback:false}};}};
 vm.createContext(context);
 const code=html.slice(html.indexOf('function g(id)'),html.indexOf('function renderResult(d)'));
 vm.runInContext(code+'\nfunction renderResult(d){globalThis.captured=d}',context);
 await vm.runInContext('calcISR()',context);
 const result=JSON.parse(JSON.stringify(context.captured));assert.ok(result);
 return Object.fromEntries(Object.entries(result).filter(([,v])=>typeof v==='number'||typeof v==='boolean'));
}
(async()=>{const rows=[];for(const [name,overrides] of cases){const fields={...baseFields,...overrides},old=await run(baseline,fields),current=await run(redesigned,fields);assert.deepEqual(current,old,name);rows.push({case:name,fields,matching_numeric_and_boolean_fields:Object.keys(old).length,baseline:old,cecil:current,passed:true});}const report={mode:'offline fixed synthetic Banxico fixtures; not live fiscal certification',baseline:'dac7118c952deeda4f6b9160c05f19b0a42ca8a0',passed:true,cases:rows};fs.writeFileSync('docs/staging/isr-parity-20261119.json',JSON.stringify(report,null,2)+'\n');console.log('6 ISR cases match main, using identical synthetic inputs and fixtures.');})();
