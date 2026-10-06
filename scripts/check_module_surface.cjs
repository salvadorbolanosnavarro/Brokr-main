/* Whole-application surface audit. Fixtures are test-only, not a live backend. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const inventory=JSON.parse(fs.readFileSync('redesign-inventory.json'));
const base=process.env.BROQUER_TEST_URL || 'http://127.0.0.1:8080';
(async()=>{
 const browser=await chromium.launch({args:['--no-sandbox']});
 const results=[];
 try {
  const ctx=await browser.newContext({ignoreHTTPSErrors:true});
  await ctx.addInitScript(()=>{localStorage.setItem('sb_token','qa-only-not-a-real-session');localStorage.setItem('sb_user',JSON.stringify({id:'00000000-0000-4000-8000-000000000001',email:'qa@example.test'}));});
  await ctx.route('**/__stage/**',async r=>{
   const u=new URL(r.request().url());let data=[];
   if(u.pathname.includes('/rest/v1/usuarios'))data=[{nombre:'Alex',rol:'agente',modulos_desactivados:[]}];
   else if(u.pathname.endsWith('/subscription/status'))data={activa:true,active:true,plan:'max'};
   else if(u.pathname.endsWith('/org'))data={tiene_org:false};
   else if(u.pathname.includes('/finanzas/resumen'))data={cuentas:[],ingresos:0,gastos:0,utilidad:0};
   else if(u.pathname.includes('/__stage/api/'))data={};
   await r.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
  fs.mkdirSync('test-results/modules',{recursive:true});
  for(const width of [1440,390]) for(const item of inventory.pages.filter(p=>!p.path.startsWith('_') && (!process.env.BROQUER_TEST_PAGES || process.env.BROQUER_TEST_PAGES.split(',').includes(p.path)))){
   const p=await ctx.newPage();await p.setViewportSize({width,height:1000});
   const errors=[];p.on('pageerror',e=>errors.push(e.message));
   try {
    await p.goto(base+'/'+item.path,{waitUntil:'load'});
    if(item.shared_shell) await p.locator('.bk-design-header').waitFor({timeout:12000});
    else await p.locator('body').waitFor();
    if(await p.locator('#splash').count()) await p.locator('#splash').waitFor({state:'hidden',timeout:10000});
    await p.evaluate(()=>document.fonts.ready);
    if(item.path==='avm.html') await p.waitForFunction(()=>document.querySelector('#root')?.childElementCount>0,{},{timeout:12000});
    const surface=await p.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,heading:document.querySelector('h1')?.textContent.trim(),controls:document.querySelectorAll('button,input,select,textarea').length}));
    if(item.shared_shell){
    await p.locator('.bk-design-assistant').click();
    assert(await p.locator('#bk-shaark-popup').isVisible(),'Broq opens');
    await p.locator('.bk-shk-close').click();
    assert(await p.locator('.bk-design-chats').isVisible(),'Chats reachable');
    }
    if(item.path==='index.html'){
      await p.locator('.bk-design-account').click();
      await p.locator('#bk-profile-drawer.is-open').waitFor({state:'visible'});
      await p.evaluate(()=>window.closeProfileDrawer());
      await p.locator('.bk-tools-menu summary').click();
      assert(await p.locator('.bk-tools-menu a[href="firmas.html"]').isVisible(),'Signature tool reachable');
      assert(await p.locator('.bk-tools-menu a[href="cumplimiento.html"]').isVisible(),'Compliance tool reachable');
      assert.equal(await p.locator('.bk-tools-menu a[href="admin.html"]').count(),0,'Admin is not shown to agent');
      await p.locator('.bk-tools-menu summary').click();
    }
    if(item.path==='contratos.html'){
      await p.locator('#doc-picker-btn').click();
      await p.locator('#doc-opt-pro').click();
      assert.match(await p.locator('#doc-picker-lbl').innerText(),/Promesa/i);
    }
    if(item.path==='cumplimiento.html'){
      await p.locator('#cp-nuevo-exp').click();
      await p.locator('#m-exp').waitFor({state:'visible',timeout:5000});
    }
    await p.screenshot({path:`test-results/modules/${item.path.replaceAll('/','_')}-${width}.png`,fullPage:true});
    results.push({page:item.path,width,...surface,errors,assistant:item.shared_shell,chats:item.shared_shell});
   }catch(e){results.push({page:item.path,width,errors,failure:e.message});}
   await p.close();
  }
  fs.writeFileSync(process.env.BROQUER_TEST_PAGES ? 'test-results/modules/focused-report.json' : 'test-results/modules/report.json',JSON.stringify({results,limitation:'Surface checks with empty fixtures; not live workflow certification.'},null,2));
  console.log(JSON.stringify({views:results.length,failures:results.filter(r=>r.failure),overflow:results.filter(r=>r.overflow).map(r=>({page:r.page,width:r.width})),javascriptErrors:results.filter(r=>r.errors.length).map(r=>({page:r.page,width:r.width,errors:r.errors}))}));
 if(results.some(r=>r.failure||r.overflow||r.errors.length)) process.exitCode=1;
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
