/* Real application scripts with test-only HTTP fixtures. No live services. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const base = process.env.BROQUER_TEST_URL || 'http://127.0.0.1:8080';
const targets = { 'buzon.html': ['/buzon', '#bz-items'], 'alertas.html': ['/alertas/requerimientos', '#al-lista'], 'crm-ajustes.html': ['/crm/catalogos', '#crm-panel'] };
const token = 'qa-only-not-a-real-session';
const userId = '00000000-0000-4000-8000-000000000001';
function catalog(admin, empty) {
  return { es_admin: admin, etapas: empty ? [] : [{ id:'etapa-qa', nombre:'Nuevo QA', color:'#C7E2F0', orden:1 }], tipos:[], fuentes:[], etiquetas:[], categorias:[] };
}
(async () => {
  const browser = await chromium.launch({ executablePath:process.env.BROQUER_CHROMIUM_EXECUTABLE || undefined, args:['--no-sandbox'] });
  const results = [];
  fs.mkdirSync('test-results/crm', { recursive:true });
  try {
    for (const width of [1440,390]) for (const role of ['agente','admin']) for (const pageName of Object.keys(targets)) for (const scenario of ['data','empty','error','loading']) {
      if(process.env.BROQUER_CRM_FILTER && !new RegExp(process.env.BROQUER_CRM_FILTER).test(`${pageName}:${width}:${role}:${scenario}`)) continue;
      const ctx = await browser.newContext({ viewport:{width,height:1000}, isMobile:width<500, ignoreHTTPSErrors:true });
      await ctx.addInitScript(({ token,userId }) => {
        localStorage.setItem('sb_token', token);
        localStorage.setItem('sb_user', JSON.stringify({id:userId,email:'qa@example.test'}));
      }, {token,userId});
      const p = await ctx.newPage(); p.setDefaultTimeout(7000); const errors = [], leaks = [], calls = [];
      let mode = scenario, release;
      const gate = new Promise(resolve => { release = resolve; });
      const lead = {id:'lead-qa',nombre:'Cliente QA',telefono:'0000000000',email:'cliente@example.test',mensaje:'Consulta ficticia sobre Casa QA',canal:'whatsapp',referencia:'conv-qa',estado:'sin_atender',asignado_a:null,propiedad_id:'prop-qa',propiedad_titulo:'Casa QA',nota_interna:''};
      const requerimiento = {id:'alerta-qa',contacto_id:'contacto-qa',contacto_nombre:'Cliente QA',agente_id:userId,activo:true,operacion:'venta',tipo_inmueble:'casa',precio_max:3000000,ciudad:'Morelia',nuevas:2};
      const leads = [lead];
      let manualPayload;
      let etapaNombre = 'Nuevo QA';
      p.on('pageerror', e => errors.push(e.message));
      await ctx.route('**/*', async route => {
        const request=route.request(),u=new URL(request.url());
        if (u.hostname !== '127.0.0.1' && u.hostname !== 'localhost') {
          if (/broquer|supabase/.test(u.hostname)) leaks.push(u.origin);
          return route.abort();
        }
        if (!u.pathname.startsWith('/__stage/')) return route.continue();
        const path=u.pathname.replace('/__stage/api','');
        let data=[],status=200;
        calls.push({method:request.method(),path});
        if(path===targets[pageName][0] && request.method()==='GET') {
          if(mode==='loading') await gate;
          if(mode==='error') return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Servicio QA temporalmente no disponible <script>invalid</script>'})});
        }
        const empty=mode==='empty';
        if (u.pathname.includes('/rest/v1/usuarios')) data=[{nombre:'Alex QA',pais:'MX',rol:role,modulos_desactivados:[]}];
        else if(path==='/subscription/status') data={activa:true,active:true,plan:'max'};
        else if(path==='/org') data={tiene_org:true,es_admin:role==='admin'};
        else if(path==='/org/miembros') data={miembros:[{user_id:userId,nombre:'Alex QA',activo:true},{user_id:'otro-qa',nombre:'Agente QA',activo:true}]};
        else if(path==='/crm/catalogos') { data=catalog(role==='admin',empty); if(data.etapas[0])data.etapas[0].nombre=etapaNombre; }
        else if(path==='/crm/etapas/etapa-qa' && request.method()==='PATCH') { etapaNombre=request.postDataJSON().nombre;data={ok:true}; }
        else if(path==='/buzon/contador') data={sin_atender:1};
        else if(path==='/buzon/respuestas') data={respuestas:[{id:'respuesta-qa',titulo:'Visita QA',canal:'todos',texto:'Hola {nombre}, sobre {inmueble}.'}]};
        else if(path==='/buzon') data={leads:empty?[]:leads.filter(l=>l.estado===(u.searchParams.get('estado')||'sin_atender')),es_admin:role==='admin'};
        else if(path==='/buzon/manual') {manualPayload=request.postDataJSON();data={...manualPayload,id:'manual-qa',estado:'sin_atender',asignado_a:null};leads.push(data);}
        else if(path==='/buzon/lead-qa' && request.method()==='PATCH') {Object.assign(lead,request.postDataJSON());data=lead;}
        else if(path==='/buzon/lead-qa/asignar') {lead.asignado_a=request.postDataJSON().user_id;data=lead;}
        else if(path==='/whatsapp2/mensajes') data={mensajes:[{body:'Mensaje ficticio QA',direction:'in',created_at:'2026-10-09T12:00:00Z'}]};
        else if(path==='/alertas/requerimientos') data={requerimientos:empty?[]:[requerimiento]};
        else if(path==='/alertas/requerimientos/alerta-qa') {Object.assign(requerimiento,request.postDataJSON());data={ok:true};}
        else if(u.pathname.includes('/rest/v1/propiedades')) data=[{id:'prop-qa',titulo:'Casa QA'}];
        else if(path.startsWith('/')) data={};
        return route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
      });
      try {
        await p.goto(base+'/'+pageName,{waitUntil:'load'});
        await p.locator('.bk-design-header').waitFor();
        const host=p.locator(targets[pageName][1]);
        if(scenario==='loading') {
          await host.locator('.bk-state--loading').waitFor();
          assert.equal(await host.getAttribute('aria-busy'),'true');
        } else if(scenario==='error') {
          await host.getByRole('alert').waitFor();
          assert(await host.getByRole('button',{name:'Volver a intentar'}).isVisible());
          assert.equal(await host.locator('script').count(),0,'API error is text, not HTML');
        } else if(scenario==='empty') {
          await host.getByText(pageName==='buzon.html'?'Todo al día':pageName==='alertas.html'?'No hay alertas':'Aún no hay etapas',{exact:true}).waitFor();
        } else {
          await host.getByText(pageName==='crm-ajustes.html'?'Nuevo QA':'Cliente QA',{exact:false}).waitFor();
          if(pageName==='crm-ajustes.html') {
            if(role==='agente') {
              assert.equal(await p.locator('#crm-etapa-add').count(),0);
              assert.equal(await p.locator('#crm-etapas button:enabled').count(),0);
              assert(await p.locator('#crm-aviso').isVisible());
            } else {
              await p.locator('[data-ren="etapa-qa"]').click();
              await p.locator('.crm-modal.is-open').waitFor();
              await p.locator('#crm-txt').fill('Negociación QA');
              assert(await p.locator('#crm-txt').evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=16));
              await p.locator('.crm-modal').getByRole('button',{name:'Guardar',exact:true}).click();
              await p.locator('#crm-etapas').getByText('Negociación QA',{exact:true}).waitFor();
              assert(calls.some(c=>c.path==='/crm/etapas/etapa-qa'&&c.method==='PATCH'));
            }
          }
          if(pageName==='buzon.html') {
            await p.locator('[data-id="lead-qa"]').click();
            await p.locator('#bz-hilo').getByText('Mensaje ficticio QA',{exact:false}).waitFor();
            assert.equal(await p.locator('#bz-asignar').count(),role==='admin'?1:0);
            if(role==='agente')assert(await p.locator('#bz-tomar').isVisible());
            await p.locator('#bz-nota').fill('Nota ficticia QA');
            await p.locator('#bz-nota-ok').click();
            await p.getByText('Nota guardada',{exact:true}).waitFor();
            await p.locator('#bz-resp').selectOption('respuesta-qa');
            assert.match(await p.locator('#bz-texto').inputValue(),/Hola Cliente, sobre Casa QA/);
            if(width<500) {
              assert.equal(await p.locator('#bz-lista-col').isVisible(),false);
              await p.locator('#bz-volver').click();
              assert(await p.locator('#bz-lista-col').isVisible());
            }
          }
          if(pageName==='buzon.html') {
            await p.locator('#bz-nuevo').click();
            const dialog=p.getByRole('dialog');
            await dialog.locator('[name=nombre]').fill('Lead QA manual');
            await dialog.locator('[name=telefono]').fill('0000000001');
            await dialog.locator('[name=email]').fill('manual@example.test');
            assert(await dialog.locator('[name=nombre]').evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=16));
            await dialog.getByRole('button',{name:'Guardar lead',exact:true}).click();
            await host.getByText('Lead QA manual',{exact:true}).waitFor();
            assert.equal(manualPayload.nombre,'Lead QA manual');
            assert.equal(manualPayload.canal,'telefono');
            assert(calls.some(c=>c.path==='/buzon/manual'&&c.method==='POST'));
          }
          if(pageName==='alertas.html') {
            await p.locator('[data-pausa="alerta-qa"]').click();
            await host.getByText('No hay alertas',{exact:true}).waitFor();
            await p.locator('#al-estado').selectOption('pausados');
            await p.locator('[data-pausa="alerta-qa"]').getByText('Reanudar',{exact:true}).waitFor();
            assert(calls.some(c=>c.path==='/alertas/requerimientos/alerta-qa'&&c.method==='PATCH'));
          }
        }
        await p.evaluate(()=>document.fonts.ready);
        const surface=await p.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,smallInputs:[...document.querySelectorAll('input,select,textarea')].filter(e=>e.getClientRects().length&&parseFloat(getComputedStyle(e).fontSize)<16).map(e=>e.id||e.name)}));
        assert.equal(surface.overflow,false,'no page overflow');assert.deepEqual(surface.smallInputs,[]);
        const image=`test-results/crm/${pageName.replace('.html','')}-${role}-${scenario}-${width}.png`;
        await p.screenshot({path:image,fullPage:true});
        if(scenario==='data' && pageName==='buzon.html' && width<500) {
          await p.locator('[data-id=lead-qa]').click();
          await p.locator('#bz-hilo .bz-msg').waitFor();
          await p.screenshot({path:image.replace('.png','-detalle.png'),fullPage:true});
        }
        if(scenario==='error') {
          mode='data';
          await host.getByRole('button',{name:'Volver a intentar'}).click();
          await host.getByText(pageName==='crm-ajustes.html'?'Nuevo QA':'Cliente QA',{exact:false}).waitFor();
        }
        assert.deepEqual(errors,[]);assert.deepEqual(leaks,[]);
        results.push({page:pageName,width,role,scenario,passed:true,image,calls});
      } catch(e) {
        console.error(JSON.stringify({page:pageName,width,role,scenario,error:e.message,errors,leaks,calls}));
        await p.screenshot({path:'test-results/crm/failure.png',fullPage:true}).catch(()=>{});
        results.push({page:pageName,width,role,scenario,passed:false,error:e.message,errors,leaks});
      } finally {release();await ctx.close();}
    }
  } finally {await browser.close();}
  const prior=process.env.BROQUER_CRM_FILTER && fs.existsSync('test-results/crm/report.json') ? JSON.parse(fs.readFileSync('test-results/crm/report.json')).results : [];
  const key=r=>`${r.page}:${r.width}:${r.role}:${r.scenario}`;
  const latest=new Map(prior.map(r=>[key(r),r])); results.forEach(r=>latest.set(key(r),r));
  fs.writeFileSync('test-results/crm/report.json',JSON.stringify({baseline:'bb6610b4',limitation:'Test-only HTTP fixtures. Chromium mobile emulation; not real iOS or real permissions/persistence.',results:[...latest.values()]},null,2));
  console.log(JSON.stringify({cases:results.length,passed:results.filter(r=>r.passed).length,failures:results.filter(r=>!r.passed)}));
  if(results.some(r=>!r.passed))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1});
