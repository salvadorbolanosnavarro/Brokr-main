/* Demo-only transport. Injected solely by BROQUER_STAGING_MODE=demo builds.
 * No backend session, keys or real customer records. Unsupported operations fail.
 */
(() => {
  'use strict';
  if (document.currentScript?.dataset.mode !== 'demo') return;
  const HOST = 'broquer-demo.invalid', KEY = 'broquer.demo.v1';
  const UID = '00000000-0000-4000-8000-000000000001';
  const ORG = '00000000-0000-4000-8000-000000000010';
  const id = n => '00000000-0000-4000-8000-' + String(n).padStart(12, '0');
  const today = () => new Date().toISOString();
  // Keep demo sessions and legacy app caches separate from connected staging.
  const storageName = key => String(key).startsWith('broquer.demo.') ? String(key) : KEY+'::'+String(key);
  for (const method of ['getItem','setItem','removeItem']) {
    const original=Storage.prototype[method];
    Storage.prototype[method]=function(key,...args) { return original.call(this,storageName(key),...args); };
  }
  const clone = x => JSON.parse(JSON.stringify(x));
  const newRow = value => ({id:crypto.randomUUID(),user_id:UID,org_id:ORG,created_at:today(),updated_at:today(),...value});
  function seed() {
    const contactos = [
      {id:id(101),nombre:'CLIENTE DEMO UNO',telefono:'0000000000',email:'cliente-uno@example.test',etapa:'nuevo',tipo:'comprador',es_potencial:true,presupuesto:3000000,etiquetas:['Demo'],notas:'Persona ficticia. No contactar.'},
      {id:id(102),nombre:'CLIENTE DEMO DOS',telefono:'0000000001',email:'cliente-dos@example.test',etapa:'activo',tipo:'vendedor',es_potencial:true,etiquetas:['Demo'],notas:'Datos ficticios para recorrer el CRM.'},
      {id:id(103),nombre:'CONTACTO DEMO TRES',telefono:'0000000002',email:'contacto-tres@example.test',etapa:'contactado',tipo:'propietario',es_potencial:false,etiquetas:[],notas:'Contacto ficticio del directorio.'}
    ].map(c=>newRow({...c,estatus:c.etapa,operaciones:[]}));
    const propiedades = [
      {id:id(201),titulo:'Casa demo en Altozano',tipo:'casa',operacion:'venta',precio:2950000,colonia:'Altozano',recamaras:3,banos:2,m2_construccion:180,m2_terreno:160},
      {id:id(202),titulo:'Departamento demo en Tres Marías',tipo:'departamento',operacion:'renta',precio:16000,colonia:'Tres Marías',recamaras:2,banos:2,m2_construccion:95,m2_terreno:95},
      {id:id(203),titulo:'Terreno demo en Jesús del Monte',tipo:'terreno',operacion:'venta',precio:1200000,colonia:'Jesús del Monte',m2_terreno:300}
    ].map(p => newRow({estatus:'activa',moneda:'MXN',ciudad:'Morelia',estado:'Michoacán',clave_interna:'DEMO-'+p.id.slice(-3),fotos:[],amenidades:[],etiquetas:['Demo'],descripcion:'Inmueble ficticio para probar la interfaz. Sin dirección ni archivos de clientes.',...p,operaciones:[{tipo:p.operacion,precio:p.precio,moneda:'MXN'}]}));
    const tareas = [0,1,2].map((n) => newRow({id:id(301+n),titulo:['Visita demo a casa en Altozano','Llamada de seguimiento demo','Preparar contrato demo'][n],fecha_entrega:new Date(Date.now()+(n+1)*86400000).toISOString(),completada:false,contacto_id:contactos[n].id,propiedad_id:propiedades[n].id,notas:'Actividad ficticia. No se enviarán recordatorios.'}));
    const contact = newRow({id:id(401),nombre:'Conversación demo',wa_id:'DEMO_NO_PHONE',etapa:'Nuevo',temperatura:'Nuevo'});
    const conv = newRow({id:id(402),contact_id:contact.id,phone_number_id:'DEMO_NO_NUMBER',ai_enabled:false,last_message_at:today()});
    const mensajes = [newRow({id:id(403),contact_id:contact.id,conversation_id:conv.id,direction:'in',sender:'lead',body:'Hola, me interesa la casa demo. ¿Podemos agendar una visita?',status:'read'}),newRow({id:id(404),contact_id:contact.id,conversation_id:conv.id,direction:'out',sender:'agent',body:'Claro. Esta conversación es ficticia y no se envía a WhatsApp.',status:'read'})];
    return {version:1,role:'agente',tables:{contactos,propiedades,tareas,usuarios:[newRow({id:UID,nombre:'Alex Demo',email:'demo@example.test',rol:'agente',plan:'max',suscripcion_activa:true,modulos_desactivados:[]})],wa_contacts:[contact],wa_conversations:[conv],wa_messages:mensajes,wa2_conversaciones:[newRow({id:conv.id,contacto_nombre:contact.nombre,no_leidos:1,ultimo_mensaje:'Conversación ficticia de demostración',updated_at:today()})],firma_documentos:[newRow({id:id(501),titulo:'Contrato demo de arrendamiento',tipo:'arrendamiento',nivel:'simple',estado:'borrador',folio:'DEMO-0001',exige_ine:false})],pipeline_etapas:[newRow({id:id(601),clave:'nuevo',nombre:'Nuevo',color:'#C7E2F0',orden:1}),newRow({id:id(602),clave:'activo',nombre:'Activo',color:'#FF944D',orden:2}),newRow({id:id(603),clave:'contactado',nombre:'Contactado',color:'#C7E2F0',orden:3})],contacto_tipos:[],fuentes_captacion:[],contacto_etiquetas:[],organizacion_categorias:[],buzon_leads:[newRow({id:id(701),nombre:contactos[0].nombre,telefono:'0000000000',email:'cliente-uno@example.test',mensaje:'Quiero conocer la casa demo en Altozano.',canal:'whatsapp',referencia:conv.id,estado:'sin_atender',asignado_a:null,propiedad_id:propiedades[0].id,propiedad_titulo:propiedades[0].titulo,ultimo_mensaje_en:today(),nota_interna:''})],buzon_respuestas:[newRow({id:id(702),titulo:'Agendar visita',texto:'Hola {nombre}, podemos revisar {inmueble}. Mensaje de demostración.',canal:'todos'})],requerimientos_busqueda:[newRow({id:id(801),contacto_id:contactos[0].id,contacto_nombre:contactos[0].nombre,agente_id:UID,activo:true,operaciones:['venta'],tipos:['casa'],zonas:['Altozano'],precio_max:3000000,moneda:'MXN',nuevas:1})],fin_cuentas:[newRow({id:id(901),nombre:'Cuenta demo',saldo_inicial:25000,activa:true})],fin_movimientos:[newRow({id:id(902),tipo:'ingreso',monto:45000,concepto:'Comisión ficticia',descripcion:'Comisión ficticia',fecha:today().slice(0,10),cuenta_id:id(901),categoria:'Comisiones'}),newRow({id:id(903),tipo:'gasto',monto:3500,concepto:'Publicidad ficticia',descripcion:'Publicidad ficticia',fecha:today().slice(0,10),cuenta_id:id(901),categoria:'Publicidad'})],fin_categorias:[]}};
  }
  let state;
  try { state=JSON.parse(localStorage.getItem(KEY)); } catch (_) {}
  if (!state || state.version!==1 || !state.tables) state=seed();
  function save() { try { localStorage.setItem(KEY,JSON.stringify(state)); } catch (_) { notice('No se pudieron conservar los cambios locales.'); } }
  function notice(message) {
    const show=()=>{let n=document.getElementById('demo-notice');if(!n){n=document.createElement('p');n.id='demo-notice';n.setAttribute('role','status');document.body.append(n);}n.textContent=message;setTimeout(()=>n.remove(),6000);};
    if(document.body) show();else document.addEventListener('DOMContentLoaded',show,{once:true});
  }
  function session() {
    const encode=o=>btoa(JSON.stringify(o)).replaceAll('=','').replaceAll('+','-').replaceAll('/','_');
    const token=encode({alg:'none',typ:'JWT'})+'.'+encode({sub:UID,exp:Math.floor(Date.now()/1000)+86400,aud:'authenticated',role:'authenticated'})+'.DEMO_NOT_A_SIGNATURE';
    localStorage.setItem('sb_token',token);localStorage.setItem('sb_refresh_token','DEMO_NO_REFRESH');localStorage.setItem('sb_refresh','DEMO_NO_REFRESH');localStorage.setItem('sb_user',JSON.stringify({id:UID,email:'demo@example.test',user_metadata:{nombre:'Alex Demo'}}));
    return {access_token:token,refresh_token:'DEMO_NO_REFRESH',token_type:'bearer',expires_in:86400,user:{id:UID,email:'demo@example.test',user_metadata:{nombre:'Alex Demo'}}};
  }
  session(); save();
  const isAdmin=()=>state.role==='admin';
  const table=name=>state.tables[name]||(state.tables[name]=[]);
  function response(data,status=200,headers={}) { return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json',...headers}}); }
  const unavailable=()=>response({detail:'Esta acción necesita el entorno conectado. En la demo no se envía, cobra ni genera contenido con servicios externos.',message:'Acción externa desactivada en la demo.'},501);
  function matches(row,params) {
    return [...params].every(([key,expression])=>{
      if(['select','order','limit','offset','on_conflict','or','and'].includes(key))return true;
      const value=row[key],at=expression.indexOf('.'),op=expression.slice(0,at),arg=expression.slice(at+1);
      if(op==='eq')return String(value)===arg;
      if(op==='neq')return String(value)!==arg;
      if(op==='is')return arg==='null'?value==null:String(value)===arg;
      if(op==='in')return arg.replace(/^\(|\)$/g,'').split(',').includes(String(value));
      if(op==='gte')return String(value)>=arg;
      if(op==='lte')return String(value)<=arg;
      if(op==='gt')return String(value)>arg;
      if(op==='lt')return String(value)<arg;
      if(op==='ilike')return String(value||'').toLowerCase().includes(arg.replaceAll('*','').replaceAll('%','').toLowerCase());
      return true;
    });
  }
  function rest(name,params,method,body) {
    if(method==='GET'||method==='HEAD') {
      let rows=table(name).filter(r=>matches(r,params)).map(clone);
      if(name==='usuarios') rows=rows.map(r=>({...r,rol:state.role}));
      if(name==='wa_conversations') rows=rows.map(r=>({...r,wa_contacts:clone(table('wa_contacts').find(c=>c.id===r.contact_id)||{})}));
      const order=params.get('order');
      if(order){const [column,direction]=order.split('.');rows.sort((a,b)=>String(a[column]??'').localeCompare(String(b[column]??''))*(direction==='desc'?-1:1));}
      const total=rows.length,offset=Number(params.get('offset')||0);rows=rows.slice(offset,offset+Number(params.get('limit')||10000));
      return response(rows,200,{'Content-Range':total?`${offset}-${offset+rows.length-1}/${total}`:'*/0'});
    }
    if(method==='POST') {
      const rows=(Array.isArray(body)?body:[body]).map(value=>{const existing=value?.id&&table(name).find(r=>r.id===value.id);if(existing){Object.assign(existing,value,{updated_at:today()});return existing;}const row=newRow(value||{});table(name).push(row);return row;});save();return response(rows,201);
    }
    if(method==='PATCH') {const rows=table(name).filter(r=>matches(r,params));rows.forEach(r=>Object.assign(r,body,{updated_at:today()}));save();return response(rows);}
    if(method==='DELETE') {state.tables[name]=table(name).filter(r=>!matches(r,params));save();return response([]);}
    return unavailable();
  }
  function finance(params) {
    const movimientos=table('fin_movimientos').filter(r=>(!params.get('desde')||r.fecha>=params.get('desde'))&&(!params.get('hasta')||r.fecha<=params.get('hasta')));
    const ingresos=movimientos.filter(r=>r.tipo==='ingreso').reduce((n,r)=>n+Number(r.monto||0),0),gastos=movimientos.filter(r=>r.tipo==='gasto').reduce((n,r)=>n+Number(r.monto||0),0);
    return {ingresos,gastos,utilidad:ingresos-gastos,cuentas:table('fin_cuentas').map(r=>({...r,saldo:Number(r.saldo_inicial||0)+ingresos-gastos})),por_categoria:[],por_mes:[],anual:{ano:new Date().getFullYear(),ingresos,gastos}};
  }
  function api(path,params,method,body) {
    if(path==='/subscription/status')return response({activa:true,active:true,plan:'max',suscripcion_activa:true,trial:false});
    if(path==='/org')return response({tiene_org:true,es_admin:isAdmin(),es_empresa:true,org_id:ORG,rol_org:isAdmin()?'admin':'agente',organizacion:{id:ORG,nombre:'Inmobiliaria Demo'},org:{id:ORG,nombre:'Inmobiliaria Demo'},miembro:{user_id:UID,rol:isAdmin()?'admin':'agente',activo:true}});
    if(path==='/org/miembros')return response({miembros:[{user_id:UID,nombre:'Alex Demo',email:'demo@example.test',rol:isAdmin()?'admin':'agente',activo:true}]});
    if(path==='/config/public')return response({});
    if(path==='/crm/catalogos')return response({es_admin:isAdmin(),etapas:table('pipeline_etapas'),tipos:table('contacto_tipos'),fuentes:table('fuentes_captacion'),etiquetas:table('contacto_etiquetas'),categorias:table('organizacion_categorias')});
    const crm=path.match(/^\/crm\/(etapas|tipos|fuentes|etiquetas|categorias)(?:\/([^/]+))?$/);
    if(crm){if(method!=='GET'&&!isAdmin())return response({detail:'Sólo un administrador puede cambiar estos ajustes.'},403);const names={etapas:'pipeline_etapas',tipos:'contacto_tipos',fuentes:'fuentes_captacion',etiquetas:'contacto_etiquetas',categorias:'organizacion_categorias'};return rest(names[crm[1]],new URLSearchParams(crm[2]?{id:'eq.'+crm[2]}:{}),method,body);}
    if(path==='/buzon/contador')return response({sin_atender:table('buzon_leads').filter(r=>r.estado==='sin_atender').length});
    if(path==='/buzon/respuestas')return method==='GET'?response({respuestas:table('buzon_respuestas')}):isAdmin()?rest('buzon_respuestas',params,method,body):response({detail:'Sólo administrador.'},403);
    if(path==='/buzon/reglas')return response({regla:{modo:'manual'},guardias:[]});
    if(path==='/buzon')return response({es_admin:isAdmin(),leads:table('buzon_leads').filter(r=>(!params.get('estado')||r.estado===params.get('estado'))&&(!params.get('canal')||r.canal===params.get('canal')))});
    if(path==='/buzon/manual'&&method==='POST'){const row=newRow({...body,estado:'sin_atender',asignado_a:null,ultimo_mensaje_en:today()});table('buzon_leads').push(row);save();return response(row,201);}
    const lead=path.match(/^\/buzon\/([^/]+)(?:\/(asignar|respondido))?$/);
    if(lead&&method!=='GET'){const row=table('buzon_leads').find(r=>r.id===lead[1]);if(!row)return response({detail:'Lead no encontrado.'},404);if(lead[2]==='asignar')row.asignado_a=body.user_id;else if(lead[2]==='respondido')row.primera_respuesta_en= today();else Object.assign(row,body);save();return response(row);}
    if(path==='/alertas/requerimientos')return response({requerimientos:table('requerimientos_busqueda')});
    const alerta=path.match(/^\/alertas\/requerimientos\/([^/]+)$/);if(alerta)return rest('requerimientos_busqueda',new URLSearchParams({id:'eq.'+alerta[1]}),method,body);
    if(path==='/whatsapp2/mensajes'&&method==='GET')return response({mensajes:table('wa_messages').filter(r=>!params.get('conversacion_id')||r.conversation_id===params.get('conversacion_id'))});
    if(path==='/finanzas/resumen')return response(finance(params));
    if(path==='/finanzas/categorias')return response({categorias:table('fin_categorias')});
    if(path==='/finanzas/comisiones-pendientes')return response({pendientes:[]});
    if(path==='/cierres/por-cobrar')return response({por_cobrar:[]});
    const fin=path.match(/^\/finanzas\/(movimientos|cuentas)(?:\/([^/]+))?$/);
    if(fin){const name=fin[1]==='movimientos'?'fin_movimientos':'fin_cuentas';if(method==='GET')return response({[fin[1]]:table(name)});return rest(name,new URLSearchParams(fin[2]?{id:'eq.'+fin[2]}:{}),method,body);}
    if(path==='/firmas/documentos'&&method==='GET')return response({documentos:table('firma_documentos')});
    if(path==='/org/tareas/contactos-vinculados')return response({contactos:table('contactos')});
    if(method==='GET' && ['/correo/cuentas','/correo/bandeja'].includes(path))return response({cuentas:[],correos:[],mensajes:[]});
    return unavailable();
  }
  const originalFetch=window.fetch.bind(window);
  window.fetch=async function(input,options={}) {
    const request=input instanceof Request?input:null;
    const url=new URL(request?request.url:String(input),location.href);
    if(url.origin===location.origin&&!url.pathname.startsWith('/__demo/'))return originalFetch(input,options);
    if(url.hostname!==HOST)return unavailable();
    const method=(options.method||request?.method||'GET').toUpperCase();
    let body=options.body;
    if(body===undefined&&request&&method!=='GET'&&method!=='HEAD')body=await request.clone().text();
    try{body=typeof body==='string'&&body?JSON.parse(body):body||{};}catch(_){return unavailable();}
    const view=sessionStorage.getItem('broquer.demo.view')||'data';
    const reading=method==='GET'&& !/\/auth\/|\/usuarios$|\/org|\/subscription\/|\/config\//.test(url.pathname);
    if(reading&&view==='loading')await new Promise(resolve=>setTimeout(resolve,1800));
    if(reading&&view==='error')return response({detail:'Error de demostración. Cambia el estado a «Con datos» para volver a intentar.'},503);
    if(url.pathname.startsWith('/supabase/auth/')) {
      if(url.pathname.endsWith('/user'))return response(session().user);
      if(url.pathname.endsWith('/token'))return response(session());
      if(url.pathname.endsWith('/logout'))return response({});
      return unavailable();
    }
    if(url.pathname.startsWith('/supabase/rest/v1/')) {
      const name=decodeURIComponent(url.pathname.slice('/supabase/rest/v1/'.length));
      if(name.startsWith('rpc/'))return unavailable();
      if(reading&&view==='empty'&&name!=='usuarios')return response([]);
      return rest(name,url.searchParams,method,body);
    }
    if(url.pathname.startsWith('/api/')) {
      const path=url.pathname.slice(4);
      const result=api(path,url.searchParams,method,body);
      if(reading&&view==='empty'&&result.ok){const d=await result.json();for(const key of Object.keys(d))if(Array.isArray(d[key]))d[key]=[];else if(typeof d[key]==='number')d[key]=0;return response(d);}
      return result;
    }
    return unavailable();
  };
  const originalOpen=window.open;
  window.open=function(url,...rest){const target=new URL(url||location.href,location.href);if(!['blob:','data:'].includes(target.protocol)&&target.origin!==location.origin){notice('Los enlaces y envíos externos están desactivados en la demo.');return null;}return originalOpen.call(window,url,...rest);};
  document.addEventListener('click',event=>{const a=event.target.closest('a[href]');if(a&&/^(mailto:|tel:|sms:|https?:\/\/wa\.me)/i.test(a.getAttribute('href'))){event.preventDefault();event.stopImmediatePropagation();notice('Contactos ficticios: no se abrirán llamadas, correos ni WhatsApp externos.');}},true);
  function toolbar() {
    const bar=document.createElement('aside');bar.id='broquer-demo-bar';bar.setAttribute('aria-label','Demostración de Broquer');
    const title=document.createElement('strong');title.textContent='Demo · datos ficticios';
    const text=document.createElement('span');const authPage=/^(login|registro|reset-password)\.html$/.test(location.pathname.split('/').pop());text.textContent=authPage?'Acceso ficticio: abre el inicio sin escribir contraseñas.':'Los cambios se guardan solo en este navegador.';if(authPage)document.querySelectorAll('input[type=password],input[type=email]').forEach(e=>{e.disabled=true;});
    const role=document.createElement('select');role.setAttribute('aria-label','Rol de demostración');role.innerHTML='<option value="agente">Agente</option><option value="admin">Administrador</option>';role.value=state.role;
    role.onchange=()=>{state.role=role.value;save();location.reload();};
    const view=document.createElement('select');view.setAttribute('aria-label','Estado de demostración');view.innerHTML='<option value="data">Con datos</option><option value="empty">Vacío</option><option value="error">Error</option><option value="loading">Carga lenta</option>';view.value=sessionStorage.getItem('broquer.demo.view')||'data';view.onchange=()=>{sessionStorage.setItem('broquer.demo.view',view.value);location.reload();};
    const reset=document.createElement('button');reset.type='button';reset.textContent='Restablecer demo';reset.onclick=()=>{if(!confirm('¿Restablecer únicamente los datos ficticios de esta demo?'))return;state=seed();save();sessionStorage.removeItem('broquer.demo.view');for(const storage of [localStorage,sessionStorage])for(let i=storage.length-1;i>=0;i--){const key=storage.key(i);if(key.startsWith(KEY+'::'))storage.removeItem(key);}location.assign('index.html');};
    const home=document.createElement('a');home.href='index.html';home.textContent='Abrir inicio';
    bar.append(title,text,role,view,reset,home);document.body.prepend(bar);
    function placeToolbar(){const head=document.querySelector('.bk-design-header');if(head)head.after(bar);}
    placeToolbar();window.addEventListener('brokr-shell-ready',placeToolbar,{once:true});
    const style=document.createElement('style');style.textContent='#broquer-demo-bar{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:10px 16px;padding:12px 20px;background:#E8F4FA;color:#192027;font:14px Manrope,Arial,sans-serif;border-bottom:1px solid #C7E2F0}#broquer-demo-bar select,#broquer-demo-bar button{font:inherit;font-size:16px;min-height:48px;max-width:100%;padding:8px 12px;border:1px solid #B9C7CE;border-radius:12px;background:white;color:#192027}#broquer-demo-bar a{color:inherit}#demo-notice{position:fixed;bottom:24px;left:16px;right:16px;z-index:10000;background:#192027;color:white;padding:16px;border-radius:12px;font:16px Manrope,Arial,sans-serif}@media(max-width:600px){#broquer-demo-bar{justify-content:flex-start}#broquer-demo-bar>span{width:100%}}';document.head.append(style);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',toolbar,{once:true});else toolbar();
})();
