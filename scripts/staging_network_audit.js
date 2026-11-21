// Opt-in QA evidence. Never include query strings, tokens, headers or bodies.
(()=>{
 if(new URLSearchParams(location.search).get('qa')!=='network')return;
 const rows=new Map();
 const render=()=>{
  let panel=document.getElementById('staging-network-audit');
  if(!panel){panel=document.createElement('aside');panel.id='staging-network-audit';panel.setAttribute('aria-label','Tráfico observado del preview');panel.style.cssText='position:fixed;bottom:12px;left:12px;z-index:2147483647;background:white;color:#111;border:1px solid #ddd;padding:16px;max-width:90vw;max-height:40vh;overflow:auto;font:14px system-ui;box-shadow:0 8px 30px #0002';document.body.append(panel);}
  panel.replaceChildren();
  const title=document.createElement('strong');title.textContent='QA · Solicitudes fetch/XHR observadas';panel.append(title);
  const list=document.createElement('ul');
  for(const text of rows.keys()){const item=document.createElement('li');item.textContent=text;list.append(item);}
  if(!rows.size){const item=document.createElement('li');item.textContent='Todavía no se observan solicitudes fetch/XHR.';list.append(item);}
  panel.append(list);
 };
 const ingest=entries=>{for(const e of entries){if(!['fetch','xmlhttprequest'].includes(e.initiatorType))continue;try{const u=new URL(e.name);rows.set(u.origin+u.pathname,true);}catch(_){}}if(document.body)render();};
 new PerformanceObserver(list=>ingest(list.getEntries())).observe({type:'resource',buffered:true});
 const start=()=>{ingest(performance.getEntriesByType('resource'));render();};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
