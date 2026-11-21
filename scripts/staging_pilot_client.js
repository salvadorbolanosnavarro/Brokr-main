/* Optional visual experience. Eligibility is always rechecked by the real API. */
(() => {
  'use strict';
  const prefix = '/cecil/';
  const inside = location.pathname.startsWith(prefix);
  function original() {
    return (inside ? '/' + location.pathname.slice(prefix.length) : location.pathname) + location.search + location.hash;
  }
  function key(id) { return 'broquer-ui-cecil:' + id; }
  function preference(id, value) {
    try { if(value === undefined) return localStorage.getItem(key(id)) === 'on'; localStorage.setItem(key(id), value ? 'on' : 'off'); } catch (_) {}
    return false;
  }
  function leave(id) { if(id) preference(id, false); location.replace(original()); }
  window.bkCecilRollout = async function({api, token, userId}) {
    if (document.getElementById('cecil-rollout-controls')) return;
    if (!token || !userId) { if(inside) leave(userId); return; }
    let state;
    try {
      const base = new URL(api, location.origin);
      if (!['https:', 'http:'].includes(base.protocol)) throw Error('API');
      const response = await fetch(base.href.replace(/\/$/, '') + '/ui/cecil', {
        headers: {Authorization:'Bearer ' + token}, cache:'no-store', signal:AbortSignal.timeout(6000)
      });
      if (!response.ok) throw Error('Eligibility');
      state = await response.json();
    } catch (_) { if(inside) leave(userId); return; }
    if (state.enabled !== true || state.user_id !== userId) { preference(userId, false); if(inside) leave(userId); return; }
    if (!inside && preference(userId)) {
      location.replace(prefix + location.pathname.replace(/^\//, '') + location.search + location.hash); return;
    }
    // Re-check revocation while the page is open, without touching auth state.
    let checking=false;
    async function refreshPilot(){
      if(checking||document.hidden)return;checking=true;
      try{
        const r=await fetch('/ui/cecil',{headers:{Authorization:'Bearer '+token},cache:'no-store',signal:AbortSignal.timeout(6000)});
        const d=r.ok?await r.json():null;
        if(!d||d.enabled!==true||d.user_id!==userId){preference(userId,false);if(inside)leave(userId);else document.getElementById('cecil-rollout-controls')?.remove();}
      }catch(_){if(inside)leave(userId);}finally{checking=false;}
    }
    setInterval(refreshPilot,15000);
    document.addEventListener('visibilitychange',refreshPilot);
    let errorsReported=0;
    function captureRuntimeError(){
      if(errorsReported++>=3)return;
      // Send only a fixed code. No raw stack, customer data, URL query or token.
      fetch('/__staging/error-probe',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({probe:'runtime-error-v1'})}).catch(()=>{});
    }
    window.addEventListener('error',captureRuntimeError);
    window.addEventListener('unhandledrejection',captureRuntimeError);
    const bar = document.createElement('aside'); bar.id = 'cecil-rollout-controls';
    bar.setAttribute('aria-label','Diseño de la aplicación');
    Object.assign(bar.style,{position:'fixed',bottom:'max(16px, env(safe-area-inset-bottom))',left:'16px',zIndex:'2147483000',maxWidth:'calc(100vw - 32px)',background:'#fff',color:'#191c1f',border:'1px solid #d5d9dd',borderRadius:'12px',padding:'12px',boxShadow:'0 4px 20px #0002',font:'14px/1.5 Arial,sans-serif'});
    if(inside) { const label=document.createElement('p');label.textContent='Cecil · Piloto de staging. Datos de prueba.';label.style.margin='0 0 8px';bar.append(label); }
    const button=document.createElement('button');button.type='button';button.textContent=inside?'Volver a Broquer':'Probar el diseño Cecil';
    Object.assign(button.style,{minHeight:'44px',font:'600 14px Arial,sans-serif',padding:'10px 16px',background:inside?'#fff':'#ff9257',border:'1px solid #d5d9dd',borderRadius:'8px',cursor:'pointer'});
    button.onclick=()=>{preference(userId,!inside);location.assign(inside?original():prefix+location.pathname.replace(/^\//,'')+location.search+location.hash);};
    bar.append(button);
    if(inside){
      const probe=document.createElement('button');probe.type='button';probe.textContent='Probar registro de errores';
      const status=document.createElement('p');status.setAttribute('role','status');status.style.margin='8px 0 0';
      probe.onclick=async()=>{probe.disabled=true;try{
        try{throw new Error('CECIL_STAGING_CONTROLLED_ERROR');}catch(controlled){if(controlled.message!=='CECIL_STAGING_CONTROLLED_ERROR')throw controlled;}
        const r=await fetch('/__staging/error-probe',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({probe:'controlled-error-v1'})});
        const d=await r.json();status.textContent=r.ok&&d.sentry_accepted&&d.receipt_saved?'Error de prueba recibido · '+d.event_id:'No se pudo confirmar la recepción del error';
      }catch(_){status.textContent='No se pudo confirmar la recepción del error';}finally{probe.disabled=false;}};
      bar.append(probe,status);
    }
    document.body.append(bar);
  };
})();
