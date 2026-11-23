/* Browser-level rollout verification. No real services, accounts or writes. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const http=require('node:http'),fs=require('node:fs'),assert=require('node:assert/strict');
let state={enabled:true,user_id:'owner'},sessionUser='owner',status=200;
const source=fs.readFileSync('ui/cecil-rollout.js','utf8');
const server=http.createServer((req,res)=>{
 if(req.url==='/ui/cecil-rollout.js'){res.setHeader('content-type','text/javascript; charset=utf-8');return res.end(source);}
 if(req.url==='/api/ui/cecil'){res.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});return res.end(JSON.stringify(state));}
 res.setHeader('content-type','text/html; charset=utf-8');res.end('<!doctype html><html><head><title>Pilot test</title></head><body><main>Existing application</main><script src="/ui/cecil-rollout.js"></script><script>bkCecilRollout({api:location.origin+"/api",token:"test-token",userId:'+JSON.stringify(sessionUser)+'})</script></body></html>');
});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 const b=await chromium.launch({executablePath:process.env.BROQUER_CHROMIUM_EXECUTABLE,args:['--no-sandbox']});let cases=0;
 try{for(const width of [1440,390]){
 const ctx=await b.newContext({viewport:{width,height:900}}),p=await ctx.newPage();
 state={enabled:true,user_id:'owner'};sessionUser='owner';status=200;
 await p.goto(base+'/index.html?source=pilot#agenda');await p.getByRole('button',{name:'Probar el diseño Cecil'}).waitFor();
 await p.getByRole('button',{name:'Probar el diseño Cecil'}).click();await p.waitForURL('**/cecil/index.html?source=pilot#agenda');await p.getByText('Cecil · Datos reales. Los cambios y envíos son reales.').waitFor();cases++;
 await p.getByRole('button',{name:'Volver a Broquer'}).click();await p.waitForURL(base+'/index.html?source=pilot#agenda');await p.getByRole('button',{name:'Probar el diseño Cecil'}).waitFor();cases++;
 await p.evaluate(()=>localStorage.setItem('broquer-ui-cecil:owner','on'));await p.reload();await p.waitForURL('**/cecil/index.html?source=pilot#agenda');await p.getByRole('button',{name:'Volver a Broquer'}).waitFor();cases++;
 state={enabled:false,user_id:'owner'};await p.reload();await p.waitForURL(base+'/index.html?source=pilot#agenda');await p.waitForTimeout(200);assert.equal(await p.locator('#cecil-rollout-controls').count(),0);assert.equal(await p.evaluate(()=>localStorage.getItem('broquer-ui-cecil:owner')),'off');cases++;
 state={enabled:true,user_id:'another-account'};await p.goto(base+'/cecil/contactos.html');await p.waitForURL(base+'/contactos.html');cases++;
 status=503;await p.goto(base+'/cecil/propiedades.html');await p.waitForURL(base+'/propiedades.html');cases++;
 status=200;state={enabled:true,user_id:'other'};sessionUser='other';await p.evaluate(()=>localStorage.setItem('broquer-ui-cecil:owner','on'));await p.goto(base+'/index.html');await p.getByRole('button',{name:'Probar el diseño Cecil'}).waitFor();assert.equal(new URL(p.url()).pathname,'/index.html');cases++;
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);cases++;await ctx.close();
 }}finally{await b.close();server.close();}console.log(JSON.stringify({passed:true,cases,widths:[1440,390],scope:'Rollout controller only; not real business workflows'}));
})().catch(e=>{console.error(e);server.close();process.exitCode=1});
