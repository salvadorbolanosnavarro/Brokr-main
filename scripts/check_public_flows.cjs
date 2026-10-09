/* Isolated UI contract checks; every service request is intercepted by Playwright. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const base=process.env.BROQUER_TEST_URL||'http://127.0.0.1:8080';
(async()=>{
 const browser=await chromium.launch({args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:390,height:900}});const requests=[];const production=[];
  context.on('request',r=>{if(/api\.broquer\.app|urtgysmtnvoqaljuhntz\.supabase\.co/.test(r.url()))production.push(r.url());});
  await context.route('**/__stage/**',async route=>{requests.push({url:route.request().url(),method:route.request().method(),body:route.request().postDataJSON()});await route.fulfill({status:200,contentType:'application/json',body:'{}'});});
  const page=await context.newPage();
  await page.goto(base+'/registro.html');
  await page.waitForURL('**/login.html');
  await page.evaluate(()=>{localStorage.setItem('sb_token','qa-only-profile');localStorage.setItem('sb_user',JSON.stringify({id:'qa-only-profile'}));});
  await page.goto(base+'/registro.html');
  assert(await page.locator('#btn-save').isDisabled(),'Profile completion requires consent');
  await page.locator('#legal-check').check();
  assert(await page.locator('#btn-save').isEnabled());
  await page.locator('#btn-save').click();
  assert.match(await page.locator('#msg').innerText(),/Ingresa tu nombre/);
  assert.equal(requests.length,0,'Empty profile must not be submitted');
  await page.locator('#legal-check').uncheck();
  assert(await page.locator('#btn-save').isDisabled());
  await page.goto(base+'/reset-password.html');
  await page.locator('#splash').waitFor({state:'hidden'});
  assert(await page.locator('#btn-reset').isDisabled(),'No reset token cannot submit');
  await page.goto(base+'/reset-password.html#access_token=qa-only-recovery&type=recovery');
  await page.reload();await page.locator('#splash').waitFor({state:'hidden'});
  assert(await page.locator('#btn-reset').isEnabled());
  await page.locator('#r-pass').fill('short');await page.locator('#r-pass2').fill('short');
  await page.locator('#btn-reset').click();assert.match(await page.locator('#msg').innerText(),/8 caracteres/);
  await page.locator('#r-pass').fill('Test-only-long123');await page.locator('#r-pass2').fill('Different123');
  await page.locator('#btn-reset').click();assert.match(await page.locator('#msg').innerText(),/no coinciden/);
  assert.equal(requests.length,0,'Invalid passwords must not be submitted');
  await page.locator('#r-pass2').fill('Test-only-long123');await page.locator('#btn-reset').click();
  await page.waitForURL('**/login.html?pwd=ok');
  assert.equal(requests.filter(r=>r.method==='PUT'&&r.url.endsWith('/auth/v1/user')).length,1);
  assert(requests.some(r=>r.method==='POST'&&r.url.includes('/auth/v1/logout?scope=global')),'Reset preserves global logout');
  for(const [file,selector] of [['unirse.html','#un-invalida'],['firmar.html','#fm-error'],['expediente.html','#ex-error']]){
   await page.goto(base+'/'+file);await page.locator(selector).waitFor({state:'visible'});
  }
  assert.deepEqual(production,[]);
  console.log('PASS: profile consent and validation; reset token/length/match checks; mocked password update and global logout; missing invitation/signature/dossier tokens; zero production requests.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
