/* Browser-level rollout verification. No real services, accounts or writes. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const http=require('node:http'),fs=require('node:fs'),assert=require('node:assert/strict');
// Server behaviour is controlled per case. `valid` is the only token the API
// accepts; any other token gets 401 (an expired Supabase JWT).
let state={enabled:true,user_id:'owner'},sessionUser='owner',status=200,valid='token-1',hang=false,seen=[];
const source=fs.readFileSync('ui/cecil-rollout.js','utf8');
const page=(user)=>'<!doctype html><html><head><title>Pilot test</title></head><body><main>Existing application<form id="f"><input name="nombre" id="nombre"><button type="submit">Guardar</button></form></main>'+
 '<script>localStorage.getItem("sb_token")||localStorage.setItem("sb_token","token-1");'+
 'window.brokrSb={refreshNow:async()=>{const r=await fetch("/api/refresh");const t=(await r.json()).token;localStorage.setItem("sb_token",t);return t;}};'+
 'document.getElementById("f").addEventListener("submit",e=>e.preventDefault());</script>'+
 '<script src="/ui/cecil-rollout.js"></script><script>bkCecilRollout({api:location.origin+"/api",getToken:()=>localStorage.getItem("sb_token"),userId:'+JSON.stringify(user)+'})</script></body></html>';
const server=http.createServer((req,res)=>{
 if(req.url==='/ui/cecil-rollout.js'){res.setHeader('content-type','text/javascript; charset=utf-8');return res.end(source);}
 if(req.url==='/ui/cecil-error-probe.js'){res.setHeader('content-type','text/javascript; charset=utf-8');return res.end(fs.readFileSync('ui/cecil-error-probe.js','utf8'));}
 if(req.url==='/api/refresh'){res.writeHead(200,{'content-type':'application/json'});return res.end(JSON.stringify({token:valid}));}
 if(req.url==='/api/ui/cecil'){
  const auth=req.headers.authorization||'';seen.push(auth);
  if(hang)return; // never answers: the client times out (network failure)
  if(auth!=='Bearer '+valid){res.writeHead(401,{'content-type':'application/json'});return res.end('{"detail":"expired"}');}
  res.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});return res.end(JSON.stringify(state));}
 res.setHeader('content-type','text/html; charset=utf-8');res.end(page(sessionUser));
});
async function reset(p){state={enabled:true,user_id:'owner'};sessionUser='owner';status=200;valid='token-1';hang=false;seen=[];await p.evaluate(()=>localStorage.setItem('sb_token','token-1'));}
// Make the 15-second revalidation run on demand.
async function tick(p){await p.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'));});await p.waitForTimeout(400);}
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 const b=await chromium.launch({executablePath:process.env.BROQUER_CHROMIUM_EXECUTABLE,args:['--no-sandbox']});let cases=0;
 try{for(const width of [1440,390]){
 const ctx=await b.newContext({viewport:{width,height:900}}),p=await ctx.newPage();
 await p.goto(base+'/index.html?source=pilot#agenda');await reset(p);await p.reload();
 await p.getByRole('button',{name:'Probar el diseño Cecil'}).click();await p.waitForURL('**/cecil/index.html?source=pilot#agenda');cases++;
 // Collapsed pilot control; opens with click, closes with Escape.
 const toggle=p.getByRole('button',{name:'Cecil · piloto'});await toggle.waitFor();
 assert.equal(await p.getByRole('button',{name:'Volver a Broquer'}).isVisible(),false);
 await toggle.click();await p.getByText('Datos reales: los cambios y envíos son reales.').waitFor();
 assert.equal(await p.getByRole('button',{name:'Probar registro de errores'}).count(),0,'probe only with ?debug=1');
 await p.keyboard.press('Escape');assert.equal(await p.getByRole('button',{name:'Volver a Broquer'}).isVisible(),false);cases++;
 const box=await toggle.boundingBox();assert.ok(box.height<=32&&box.width<=160,'small control: '+JSON.stringify(box));cases++;
 await toggle.click();await p.getByRole('button',{name:'Volver a Broquer'}).click();await p.waitForURL(base+'/index.html?source=pilot#agenda');await p.getByRole('button',{name:'Probar el diseño Cecil'}).waitFor();cases++;
 await p.evaluate(()=>localStorage.setItem('broquer-ui-cecil:owner','on'));await p.reload();await p.waitForURL('**/cecil/index.html?source=pilot#agenda');await p.getByRole('button',{name:'Cecil · piloto'}).waitFor();cases++;
 // Debug probe only with ?debug=1.
 await p.goto(base+'/cecil/index.html?debug=1');await p.getByRole('button',{name:'Cecil · piloto'}).click();await p.getByRole('button',{name:'Probar registro de errores'}).waitFor();cases++;

 // 1) Expired token while inside: refresh and stay.
 await p.goto(base+'/cecil/contratos.html');await p.getByRole('button',{name:'Cecil · piloto'}).waitFor();
 valid='token-2';seen=[];await tick(p);
 assert.equal(new URL(p.url()).pathname,'/cecil/contratos.html','expired token must not leave Cecil');
 assert.ok(seen.includes('Bearer token-1')&&seen.includes('Bearer token-2'),'retried with refreshed token: '+seen);
 seen=[];await tick(p);assert.deepEqual(seen,['Bearer token-2'],'later checks read the current token');cases++;
 // 2) Network failure / timeout: stay.
 hang=true;await p.evaluate(()=>{const f=window.fetch;window.fetch=(u,o)=>String(u).includes('/ui/cecil')?Promise.reject(new TypeError('Failed to fetch')):f(u,o);});
 await tick(p);assert.equal(new URL(p.url()).pathname,'/cecil/contratos.html','network error must not leave Cecil');cases++;
 await p.reload();hang=false;status=503;await p.getByRole('button',{name:'Cecil · piloto'}).waitFor();await tick(p);
 assert.equal(new URL(p.url()).pathname,'/cecil/contratos.html','5xx must not leave Cecil');cases++;
 // Initial load with the server down also stays.
 status=503;await p.goto(base+'/cecil/propiedades.html');await p.getByRole('button',{name:'Cecil · piloto'}).waitFor();assert.equal(new URL(p.url()).pathname,'/cecil/propiedades.html');cases++;
 // 3) Explicit revocation with unsaved changes: wait for save, then leave.
 status=200;await p.goto(base+'/cecil/contratos.html');await p.getByRole('button',{name:'Cecil · piloto'}).waitFor();
 await p.fill('#nombre','Contrato a medias');state={enabled:false,user_id:'owner'};await tick(p);
 assert.equal(new URL(p.url()).pathname,'/cecil/contratos.html','unsaved form keeps the page');
 await p.getByText('El piloto terminó. Guarda tus cambios y volverás a Broquer.').waitFor();cases++;
 await p.getByRole('button',{name:'Guardar'}).click();await p.waitForURL(base+'/contratos.html',{timeout:8000});
 assert.equal(await p.evaluate(()=>localStorage.getItem('broquer-ui-cecil:owner')),'off');
 assert.ok(await p.evaluate(()=>localStorage.getItem('sb_token')),'session kept');cases++;
 // 4) Explicit revocation without changes: leave on the next check.
 await reset(p);await p.goto(base+'/cecil/contactos.html');await p.getByRole('button',{name:'Cecil · piloto'}).waitFor();
 state={enabled:false,user_id:'owner'};await tick(p);await p.waitForURL(base+'/contactos.html');cases++;
 // Different account: leave.
 await reset(p);state={enabled:true,user_id:'another-account'};await p.goto(base+'/cecil/contactos.html');await p.waitForURL(base+'/contactos.html');cases++;
 // Disabled on load from Broquer: no button, preference cleared.
 await reset(p);state={enabled:false,user_id:'owner'};await p.goto(base+'/index.html');await p.waitForTimeout(300);assert.equal(await p.locator('#cecil-rollout-controls').count(),0);assert.equal(await p.evaluate(()=>localStorage.getItem('broquer-ui-cecil:owner')),'off');cases++;
 // Another session user never inherits someone else's preference.
 await reset(p);state={enabled:true,user_id:'other'};sessionUser='other';await p.evaluate(()=>localStorage.setItem('broquer-ui-cecil:owner','on'));await p.goto(base+'/index.html');await p.getByRole('button',{name:'Probar el diseño Cecil'}).waitFor();assert.equal(new URL(p.url()).pathname,'/index.html');cases++;
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);cases++;await ctx.close();
 }}finally{await b.close();server.close();}console.log(JSON.stringify({passed:true,cases,widths:[1440,390],scope:'Rollout controller only; not real business workflows'}));
})().catch(e=>{console.error(e);server.close();process.exitCode=1});
