/* Controlled diagnostic, loaded only after server eligibility in the pilot. */
(() => {
  window.bkCecilErrorProbe = function (bar) {
    const button=document.createElement('button'),status=document.createElement('p');
    button.type='button';button.textContent='Probar registro de errores';
    Object.assign(button.style,{display:'block',marginTop:'8px',minHeight:'44px',fontSize:'14px'});
    status.setAttribute('role','status');status.style.margin='4px 0 0';
    button.onclick=async()=>{
      button.disabled=true;status.textContent='Comprobando recepción…';
      try {
        const S=window.Sentry;
        const client=S?.getClient?.() || S?.getCurrentHub?.().getClient?.();
        if(!client?.on || !S?.captureEvent || !S?.withScope)throw Error('SDK unavailable');
        const eventId=crypto.randomUUID().replaceAll('-','');
        const receipt=new Promise(resolve=>{
          let unsubscribe;
          const timer=setTimeout(()=>{unsubscribe?.();resolve(false);},10000);
          unsubscribe=client.on('afterSendEvent',(event,response)=>{
            if(event.event_id!==eventId)return;
            clearTimeout(timer);if(typeof unsubscribe==='function')unsubscribe();
            resolve(response?.statusCode>=200 && response.statusCode<300);
          });
        });
        S.withScope(scope=>{
          scope.addEventProcessor(event=>{
            delete event.user;delete event.request;event.breadcrumbs=[];event.extra={};return event;
          });
          S.captureEvent({event_id:eventId,message:'CECIL_PILOT_CONTROLLED_TEST',level:'error',
            tags:{cecil_pilot_probe:'1'},breadcrumbs:[],user:{},request:{}});
        });
        Promise.resolve(S.flush?.(6000)).catch(()=>{});
        status.textContent=await receipt?'Sentry aceptó el error de prueba · '+eventId:'No se pudo confirmar la recepción del error';
      }catch(_){status.textContent='No se pudo confirmar la recepción del error';}
      finally{button.disabled=false;}
    };
    bar.append(button,status);
  };
})();
