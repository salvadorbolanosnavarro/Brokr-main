/* Test the actual compiled demo, without Playwright API fixtures. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
const base=process.env.BROQUER_TEST_URL||'http://127.0.0.1:8084';
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.BROQUER_CHROMIUM_EXECUTABLE,args:['--no-sandbox']});
 const reports=[];
 try{
  for(const width of [1440,390]){
   const ctx=await browser.newContext({viewport:{width,height:1000},isMobile:width<500});
   const leaks=[];
   ctx.on('request',r=>{if(/broquer-demo\.invalid|api\.broquer\.app|urtgysmtnvoqaljuhntz/.test(r.url()))leaks.push(r.url());});
   const p=await ctx.newPage();p.setDefaultTimeout(8000);
   let errors=[];p.on('pageerror',e=>errors.push(e.message));
   fs.mkdirSync('test-results/demo',{recursive:true});
   for(const name of ['index','clientes','propiedades','tareas','finanzas','buzon','alertas','crm-ajustes','bandeja']){
    errors=[];
    await p.goto(base+'/'+name+'.html',{waitUntil:'load'});
    await p.locator('.bk-design-header').waitFor();
    await p.locator('#broquer-demo-bar').waitFor();
    await p.evaluate(()=>document.fonts.ready);
    if(name==='clientes')await p.getByText('CLIENTE DEMO UNO',{exact:true}).first().waitFor();
    if(name==='propiedades')await p.getByText('Casa demo en Altozano',{exact:true}).first().waitFor();
    if(name==='buzon')await p.locator('.bz-item').waitFor();
    const surface=await p.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,smallInputs:[...document.querySelectorAll('input,select,textarea')].filter(e=>e.getClientRects().length&&parseFloat(getComputedStyle(e).fontSize)<16).map(e=>e.id)}));
    assert.equal(surface.overflow,false,name+' overflow');assert.deepEqual(surface.smallInputs,[],name+' small inputs');assert.deepEqual(errors,[],name+' JS errors');
    await p.screenshot({path:`test-results/demo/${name}-${width}.png`,fullPage:true});
    reports.push({page:name,width,...surface,errors});
   }
   await p.goto(base+'/clientes.html');await p.locator('#add-btn-top').click();
   await p.locator('#m-nombre').fill('CLIENTE CREADO EN DEMO');await p.locator('#m-tel').fill('0000000009');
   await p.getByRole('button',{name:'Guardar cliente',exact:true}).click();
   await p.getByText('CLIENTE CREADO EN DEMO',{exact:true}).first().waitFor();await p.reload();
   await p.getByText('CLIENTE CREADO EN DEMO',{exact:true}).first().waitFor();
   await p.goto(base+'/tareas.html');await p.locator('.btn-new-tarea').click();await p.locator('#tn-titulo').fill('TAREA CREADA EN DEMO');await p.locator('#tn-crear').click();
   await p.getByText('TAREA CREADA EN DEMO',{exact:true}).first().waitFor();await p.reload();await p.getByText('TAREA CREADA EN DEMO',{exact:true}).first().waitFor();
   await p.goto(base+'/finanzas.html');await p.locator('#fin-btn-nuevo').click();await p.locator('#fin-f-monto').fill('750');await p.locator('#fin-f-concepto').fill('MOVIMIENTO CREADO EN DEMO');await p.locator('#fin-f-guardar').click();
   await p.getByText('MOVIMIENTO CREADO EN DEMO',{exact:true}).first().waitFor();await p.reload();await p.getByText('MOVIMIENTO CREADO EN DEMO',{exact:true}).first().waitFor();
   await p.goto(base+'/crm-ajustes.html');await p.getByLabel('Rol de demostración').selectOption('admin');await p.locator('#crm-etapa-add').waitFor();
   const blocked=await p.evaluate(async()=>{const r=await fetch('https://broquer-demo.invalid/api/whatsapp2/mensajes',{method:'POST',body:JSON.stringify({texto:'No se envía'})});return r.status;});assert.equal(blocked,501);
   await p.getByLabel('Estado de demostración').selectOption('error');await p.locator('#crm-panel [role=alert]').waitFor();
   await p.getByLabel('Estado de demostración').selectOption('data');await p.locator('#crm-etapa-add').waitFor();
   p.once('dialog',d=>d.accept());await p.getByRole('button',{name:'Restablecer demo'}).click();await p.waitForURL('**/index.html');
   await p.goto(base+'/clientes.html');await p.getByText('CLIENTE DEMO UNO',{exact:true}).first().waitFor();assert.equal(await p.getByText('CLIENTE CREADO EN DEMO',{exact:true}).count(),0);
   assert.deepEqual(leaks,[],'all demo API requests stay inside the browser');
   await ctx.close();
  }
 }finally{await browser.close();}
 const report={reports,checks:['client creation persists on reload','task creation persists on reload','finance movement persists on reload','role switching','error state switching','external send returns 501','reset clears demo edits','zero API/Supabase network requests'],limitations:'Local browser simulation only; not real backend, RLS or iOS WebView.'};
 fs.writeFileSync('test-results/demo/report.json',JSON.stringify(report,null,2));console.log(JSON.stringify({views:reports.length,checks:report.checks,passed:true}));
})().catch(e=>{console.error(e);process.exitCode=1});
