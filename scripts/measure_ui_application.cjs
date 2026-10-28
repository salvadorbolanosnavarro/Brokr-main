/* Application-wide measured evidence. Demo browser data only; no live writes. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs');
const base=process.env.BROQUER_TEST_URL||'http://127.0.0.1:8084';
const inventory=JSON.parse(fs.readFileSync('redesign-inventory.json'));
const targets=inventory.pages.filter(x=>!x.path.startsWith('_')).map(x=>x.path);
const selected=process.env.BROQUER_TEST_PAGES?.split(',');
const jobs=[1440,390].flatMap(width=>targets.filter(p=>!selected||selected.includes(p)).map(page=>({width,page})));
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.BROQUER_CHROMIUM_EXECUTABLE,args:['--no-sandbox']});
 const results=[];fs.mkdirSync('test-results/ui-application',{recursive:true});
 async function run(job){
  const ctx=await browser.newContext({viewport:{width:job.width,height:1000},isMobile:job.width===390});
  await ctx.addInitScript(()=>{
   window.__qaCalls=[];const wrap=fn=>function(input,options){const raw=typeof input==='string'?input:input.url;let call;try{const u=new URL(raw,location.href);if(u.hostname==='broquer-demo.invalid'){call={method:(options?.method||input?.method||'GET').toUpperCase(),path:u.pathname,status:null};window.__qaCalls.push(call);}}catch{}const result=fn.apply(this,arguments);if(call)Promise.resolve(result).then(r=>call.status=r.status,()=>call.status=0);return result;};let current=wrap(window.fetch);Object.defineProperty(window,'fetch',{configurable:true,get:()=>current,set:fn=>{current=wrap(fn);}});
  });
  await ctx.route('**/*' ,route=>{const u=new URL(route.request().url());return ['127.0.0.1','localhost'].includes(u.hostname)||['blob:','data:'].includes(u.protocol)?route.continue():route.abort();});
  const p=await ctx.newPage();p.setDefaultTimeout(8000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
  try{
   await p.goto(base+'/'+job.page,{waitUntil:'load',timeout:20000});
   if(inventory.pages.find(x=>x.path===job.page)?.shared_shell)await p.locator('.bk-design-header').waitFor({state:'visible'});await p.waitForTimeout(700);await p.evaluate(()=>document.fonts.ready);await p.evaluate(()=>window.scrollTo(0,0));
   const measured=await p.evaluate(()=>{
    const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none'&&getComputedStyle(e).opacity!=='0';
    const h1=document.querySelector('h1');
    const buttons=[...document.querySelectorAll('button')].filter(visible).map(e=>{const s=getComputedStyle(e);return {id:e.id,class:e.className,text:e.textContent.trim().slice(0,45),kind:e.dataset.uiKind||null,size:e.dataset.uiSize||null,disabled:e.disabled,selected:e.dataset.uiSelected||null,height:Math.round(e.getBoundingClientRect().height),font:s.fontSize,radius:s.borderRadius,background:s.backgroundColor,color:s.color,weight:s.fontWeight};});
    const smallFields=[...document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]),select,textarea')].filter(visible).filter(e=>parseFloat(getComputedStyle(e).fontSize)<16).map(e=>e.id||e.name);
    const fontSizes={};for(const e of document.querySelectorAll('body *'))if(visible(e)&&[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())){const size=getComputedStyle(e).fontSize;(fontSizes[size]??=[]).push(e.id||e.className||e.tagName);}
    const overlaps=[];for(const group of document.querySelectorAll('.filters-row,.props-toolbar,.tk-toolbar,.bl-filtros,.fin-periodo')){const items=[...group.children].filter(visible);for(let i=0;i<items.length;i++)for(let j=i+1;j<items.length;j++){const a=items[i].getBoundingClientRect(),b=items[j].getBoundingClientRect();if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>2&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>2)overlaps.push([items[i].id||items[i].className,items[j].id||items[j].className]);}}
    const clippedKpis=[...document.querySelectorAll('.fin-kpi-val')].filter(e=>e.scrollWidth>e.clientWidth+1||e.getBoundingClientRect().height>parseFloat(getComputedStyle(e).lineHeight)+1).map(e=>e.id);return {clippedKpis,overlaps,url:location.pathname,title:document.title,h1:h1?{text:h1.textContent.trim(),size:getComputedStyle(h1).fontSize}:null,overflow:document.documentElement.scrollWidth>innerWidth,offenders:[...document.querySelectorAll('body *')].filter(visible).filter(e=>e.getBoundingClientRect().right>innerWidth+1&&getComputedStyle(e).position!=='fixed').slice(0,10).map(e=>e.id||e.className||e.tagName),smallFields,buttons,fontSizes,calls:window.__qaCalls||[],dateFields:document.querySelectorAll('input[type=date]').length,spanishDates:document.querySelectorAll('.ui-date-trigger').length};
   });
   await p.screenshot({path:`test-results/ui-application/${job.page.replaceAll('/','_')}-${job.width}.png`});results.push({...job,...measured,errors});
  }catch(e){results.push({...job,errors,failure:e.message});}finally{await ctx.close();}
 }
 try{let cursor=0;await Promise.all(Array.from({length:3},async()=>{while(cursor<jobs.length){const job=jobs[cursor++];await run(job);}}));}finally{await browser.close();}
 results.sort((a,b)=>a.page.localeCompare(b.page)||b.width-a.width);
 const crypto=require('crypto');const hashes={};for(const directory of ['.','ui','styles','preview-modo','videos'])for(const file of fs.readdirSync(directory)){const name=directory==='.'?file:directory+'/'+file;if(/\.(html|css|js)$/.test(file)&&fs.statSync(name).isFile())hashes[name]=crypto.createHash('sha256').update(fs.readFileSync(name)).digest('hex');}fs.writeFileSync('test-results/ui-application/report.json',JSON.stringify({mode:'demo',hashes,scope:'Rendered surfaces; not real backend/RLS, workflow completeness or native iOS certification.',results},null,2));
 const summary={views:results.length,failures:results.filter(r=>r.failure),errors:results.filter(r=>r.errors.length).map(r=>({page:r.page,width:r.width,errors:r.errors})),clippedKpis:results.filter(r=>r.clippedKpis?.length).map(r=>({page:r.page,width:r.width,fields:r.clippedKpis})),overlaps:results.filter(r=>r.overlaps?.length).map(r=>({page:r.page,width:r.width,controls:r.overlaps})),overflow:results.filter(r=>r.overflow).map(r=>({page:r.page,width:r.width,offenders:r.offenders})),smallFields:results.filter(r=>r.smallFields?.length).map(r=>({page:r.page,width:r.width,fields:r.smallFields}))};
 console.log(JSON.stringify(summary,null,2));if(summary.failures.length||summary.errors.length||summary.overflow.length||summary.smallFields.length||summary.overlaps.length||summary.clippedKpis.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1});
