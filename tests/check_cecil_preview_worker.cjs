const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const manifest=JSON.parse(fs.readFileSync('preview-public-manifest.json','utf8'));
 const source=fs.readFileSync('_worker.js','utf8').replace("import manifest from './preview-public-manifest.json';",'const manifest='+JSON.stringify(manifest)+';');
 const worker=(await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))).default;
 let calls=[];
 const env={ASSETS:{fetch:async r=>{calls.push(new URL(r.url).pathname);return new Response('staging-asset',{headers:{'Content-Type':'text/html'}});}}};
 for(const path of ['/','/landing','/landing.html','/cecil/login','/app-shell.js']){
  const r=await worker.fetch(new Request('https://work-cecil-staging-preview-2.broquer-staging.pages.dev'+path),env);
  assert.equal(r.status,200,path);assert.equal(r.headers.get('X-Cecil-Preview'),'staging-only');assert.ok(calls.at(-1).startsWith('/preview-public/'));
  assert.ok(!r.headers.get('Content-Security-Policy').includes('api.broquer.app'));
 }
 for(const path of ['/main.py','/scripts/build_staging.py','/login.html.bak','/preview-public/login','/preview-public-manifest.json','/../core/config.py']){
  const count=calls.length;const r=await worker.fetch(new Request('https://work-cecil-staging-preview-2.broquer-staging.pages.dev'+path),env);
  assert.equal(r.status,404,path);assert.equal(calls.length,count);
 }
 assert.equal((await worker.fetch(new Request('https://app.broquer.app/'),env)).status,503);
 assert.equal((await worker.fetch(new Request('https://work-cecil-staging-preview-2.broquer-staging.pages.dev/',{method:'POST'}),env)).status,405);
 console.log('13 preview routing checks passed; source and non-staging hosts denied.');
})();
