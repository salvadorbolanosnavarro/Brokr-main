/* Render EVERY published HTML at iPhone width. Offline mocked services only.
 * No real sessions, credentials, external requests, sends or writes.
 */
const {chromium,webkit}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const ROOT=path.resolve('preview-public'), manifest=JSON.parse(fs.readFileSync('preview-public-manifest.json','utf8'));
const pages=Object.keys(manifest).filter(n=>n.endsWith('.html')).sort();
const user={id:'11111111-1111-4111-8111-111111111111',email:'mobile-test@example.invalid',email_confirmed_at:'2026-11-21T00:00:00Z',user_metadata:{nombre:'QA móvil',telefono:'0000000000'}};
const profile={id:user.id,nombre:'QA móvil',telefono:'0000000000',email:user.email,rol:'admin',plan:'pro',pais:'MX',activo:true,acceso_completo_hasta:'2099-01-01T00:00:00Z',modulos_desactivados:[]};
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.woff2':'font/woff2','.woff':'font/woff'};
const server=http.createServer((req,res)=>{
 const relative=decodeURIComponent(new URL(req.url,'http://localhost').pathname).replace(/^\//,'')||'index.html';
 const file=path.resolve(ROOT,relative);
 if(!file.startsWith(ROOT+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);return res.end('Not found');}
 res.setHeader('content-type',(mime[path.extname(file)]||'application/octet-stream')+'; charset=utf-8');res.end(fs.readFileSync(file));
});
function auditDOM(injectNegative=false){
 if(injectNegative){const x=document.createElement('input');x.id='qa-negative-small-field';x.style.setProperty('font-size','13px','important');document.body.append(x);}
 const fields=[...document.querySelectorAll('input:not([type="hidden"]),select,textarea')].map(el=>{
  const style=getComputedStyle(el),r=el.getBoundingClientRect();
  return {id:el.id||null,tag:el.tagName,type:el.getAttribute('type'),fontSize:parseFloat(style.fontSize),inlineFont:el.style.getPropertyValue('font-size'),inlinePriority:el.style.getPropertyPriority('font-size'),visible:!!el.getClientRects().length&&r.width>0&&r.height>0&&style.visibility!=='hidden'&&style.visibility!=='collapse'};
 });
 const gesture=new Event('gesturestart',{bubbles:true,cancelable:true});document.dispatchEvent(gesture);
 const touchActions=[document.documentElement,document.body,document.querySelector('.bk-page')].filter(Boolean).map(e=>getComputedStyle(e).touchAction);
 return {touchActions,fields,below:fields.filter(e=>!Number.isFinite(e.fontSize)||e.fontSize<16),viewport:document.querySelector('meta[name="viewport"]')?.content||'',pinchPrevented:gesture.defaultPrevented,cssLoaded:[...document.styleSheets].some(s=>s.href?.endsWith('/staging-mobile-fields.css'))};
}
(async()=>{
 assert(pages.filter(n=>n.startsWith('cecil/')).length>=53,'Do not omit Cecil screens');
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const origin='http://127.0.0.1:'+server.address().port, report={width:390,scope:'Published HTML + executed shell, mocked authentication/services; legacy delayed font repair disabled for CSS audit; not a physical iPhone test',engines:[]};
 for(const engine of (process.env.MOBILE_TEST_BROWSERS||'chromium').split(',')){
  const browser=await ({chromium,webkit}[engine]).launch({...(engine==='chromium'&&process.env.BROQUER_CHROMIUM_EXECUTABLE?{executablePath:process.env.BROQUER_CHROMIUM_EXECUTABLE}:{}),...(engine==='chromium'?{args:['--no-sandbox']}: {})});
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,serviceWorkers:'block'});
  let disableFix=false,disableLegacyFloor=true,legacyRepairScriptsBlocked=0;
  await context.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());
   if(u.origin===origin){
    // This old MutationObserver repairs fonts after load and would mask CSS
    // regressions (including the iOS focus-before-repair bug). Audit CSS alone.
    if(u.pathname.endsWith('/mobile-inputs.js')&&disableLegacyFloor){legacyRepairScriptsBlocked++;return route.fulfill({status:200,contentType:'text/javascript',body:''});}
    if(u.pathname==='/staging-mobile-fields.css'&&disableFix)return route.fulfill({status:200,contentType:'text/css',body:''});
    if(u.pathname==='/ui/cecil')return route.fulfill({json:{enabled:true,user_id:user.id}});
    return route.continue();
   }
   // Fulfill every outside request locally: network writes are impossible.
   if(req.resourceType()==='script')return route.fulfill({contentType:'text/javascript',body:''});
   if(req.resourceType()==='stylesheet')return route.fulfill({contentType:'text/css',body:''});
   let data=[];
   if(u.pathname.includes('/auth/v1/user'))data=user;
   else if(u.pathname.includes('/auth/v1/token'))data={user,access_token:'offline-test-token'};
   else if(u.pathname.includes('/rest/v1/usuarios'))data=[profile];
   else if(u.pathname==='/org')data={id:'offline-org',nombre:'QA',rol:'admin',miembros:[]};
   else if(u.pathname==='/ui/cecil')data={enabled:true,user_id:user.id};
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
  });
  await context.addInitScript(({user,profile})=>{
   // Synthetic state exists only in this disposable local regression browser.
   const name=location.pathname.split('/').pop();
   if(['login.html','landing.html','reset-password.html'].includes(name)){localStorage.clear();sessionStorage.clear();return;}
   localStorage.setItem('sb_token','offline-test-token');localStorage.setItem('sb_user',JSON.stringify(user));
   localStorage.setItem('sesion_activa','true');localStorage.setItem('broquer-ui-cecil:'+user.id,'off');
  },{user,profile});
  const page=await context.newPage(), rows=[];
  async function visit(name){
   try{await page.goto(origin+'/'+name,{waitUntil:'networkidle'});}catch(e){if(!/interrupted by another navigation/.test(e.message))throw e;await page.waitForLoadState('networkidle');}
   assert.equal(new URL(page.url()).origin,origin,'Screen escaped the offline test origin');
   if(await page.locator('script[src$="app-shell.js"]').count())await page.locator('#bk-cmdk-input').waitFor({state:'attached',timeout:3000}).catch(()=>{});
   await page.evaluate(()=>document.fonts.ready);
   return page.evaluate(auditDOM);
  }
  try{
   // Negative control: prove the assertion catches the reported regression.
   disableFix=true;await visit('cecil/isr.html');
   assert(await page.locator('#f-tipo').count(),'ISR fixture did not render: '+page.url());
   // Inject and measure in ONE task, before any legacy repair can run.
   const negative=await page.evaluate(auditDOM,true);
   console.log(engine+' negative control '+JSON.stringify({below:negative.below,cssLoaded:negative.cssLoaded}));
   assert(negative.below.some(e=>e.id==='qa-negative-small-field'),'Negative control must detect an actual rendered field below16px');
   disableFix=false;
   for(const name of pages){
    console.log(engine+' auditing '+name);
    let a=await visit(name);
    assert(a.cssLoaded,engine+' '+name+': global mobile stylesheet missing');
    assert(!a.below.length,engine+' '+name+': fields below16px '+JSON.stringify(a.below));
    assert(!a.fields.some(e=>e.inlinePriority==='important'&&e.inlineFont==='16px'),engine+' '+name+': delayed JS font repair masked CSS sizing');
    assert(!/user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*(?:0(?:\.\d*)?|1(?:\.0*)?)(?:\s*[,;]|\s*$)/i.test(a.viewport),engine+' '+name+': pinch zoom disabled');
    assert(!a.pinchPrevented,engine+' '+name+': gesturestart prevented');
    assert(a.touchActions.every(x=>x==='auto'||x==='manipulation'||x.includes('pinch-zoom')),engine+' '+name+': CSS blocks pinch '+JSON.stringify(a.touchActions));
    const row={page:name,resolved:new URL(page.url()).pathname,fields:a.fields.length,visible:a.fields.filter(e=>e.visible).length,shellFields:[]};
    // Open the real command/assistant UI where present; audit active styles too.
    if(await page.locator('#bk-cmdk-input').count()){
     await page.keyboard.press('Control+k');
     await page.locator('#bk-cmdk-input').waitFor({state:'visible'});
     a=await page.evaluate(auditDOM);assert(!a.below.length,name+': command palette '+JSON.stringify(a.below));
     row.shellFields.push('bk-cmdk-input');await page.keyboard.press('Escape');
    }
    if(await page.locator('#bk-shk-input').count()){
     const opener=page.getByRole('button',{name:'Abrir Cecil IA',exact:true});
     if(await opener.isVisible())await opener.click();
     else if(await page.locator('#bk-shaark-fab').isVisible())await page.locator('#bk-shaark-fab').click();
     a=await page.evaluate(auditDOM);assert(!a.below.length,name+': assistant '+JSON.stringify(a.below));
     row.shellFields.push('bk-shk-input');
    }
    if(await page.locator('#bk-search').count()){
     row.shellFields.push('bk-search');
     const toggle=page.locator('#bk-search-toggle');
     if(await toggle.isVisible()){await toggle.click();a=await page.evaluate(auditDOM);assert(!a.below.length,name+': expanded global search '+JSON.stringify(a.below));}
    }
    rows.push(row);
   }
   assert(rows.filter(r=>r.page.startsWith('cecil/')&&r.shellFields.includes('bk-cmdk-input')).length>=21,'Authenticated shell coverage unexpectedly missing');
   // A field inserted after page load inherits the same rule (no JS sizing).
   await visit('cecil/isr.html');
   const dynamic=await page.evaluate(()=>{const x=document.createElement('input');x.id='qa-dynamic';x.style.fontSize='11px';document.body.append(x);return parseFloat(getComputedStyle(x).fontSize);});
   assert(dynamic>=16,'Dynamically inserted field is smaller than16px');
   // Desktop stays at its original size with and without the mobile CSS.
   await page.setViewportSize({width:1280,height:900});disableLegacyFloor=false;disableFix=false;await visit('cecil/isr.html');const desktopWith=await page.locator('#f-tipo').evaluate(e=>getComputedStyle(e).fontSize);
   disableFix=true;await visit('cecil/isr.html');const desktopWithout=await page.locator('#f-tipo').evaluate(e=>getComputedStyle(e).fontSize);
   assert.equal(desktopWith,desktopWithout,'Mobile rule changed desktop typography');
   report.engines.push({engine,legacyRepairScriptsBlocked,pages:rows.length,cecilPages:rows.filter(r=>r.page.startsWith('cecil/')).length,negativeControlBelow16:negative.below.map(e=>e.id),dynamicField:dynamic,desktopWith,desktopWithout,results:rows});
  }finally{await context.close();await browser.close();}
 }
 const reportPath=process.argv[2]||'/tmp/cecil-mobile-fields-390.json';fs.writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({passed:true,width:390,engines:report.engines.map(e=>({engine:e.engine,pages:e.pages,cecilPages:e.cecilPages,fields:e.results.reduce((n,r)=>n+r.fields,0),visible:e.results.reduce((n,r)=>n+r.visible,0),negativeControlFields:e.negativeControlBelow16.length,desktopUnchanged:e.desktopWith===e.desktopWithout})),report:reportPath}));
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>server.close());
