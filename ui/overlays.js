/* Focus, Escape and accessibility for the existing modal open/close handlers. */
(() => {
 'use strict';if(window.__broquerOverlays)return;window.__broquerOverlays=true;
 const specs=[['#modal-ov','[data-ui-modal]','cerrarModal','Contacto'],['#prop-modal','[data-ui-modal]','closePropModal','Inmueble'],['#bk-profile-drawer',null,'closeProfileDrawer','Mi cuenta']];
 const states=new Map();let invoker;
 const visible=e=>e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).opacity!=='0';
 const focusables=e=>[...e.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled):not([type=hidden]),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')].filter(visible);
 document.addEventListener('pointerdown',e=>{if(!e.target.closest('[data-ui-modal],#bk-profile-drawer'))invoker=e.target.closest('button,a')||document.activeElement;},true);
 function update(){
  const candidates=[...specs];
  for(const host of document.querySelectorAll('.bk-overlay[id]')){
   const panel=host.querySelector('.bk-modal');if(!panel)continue;
   const close=()=>{const button=panel.querySelector('[aria-label="Cerrar"],.bk-modal__close,.bk-modal__x')||[...panel.querySelectorAll('button')].find(b=>b.textContent.trim()==='Cancelar');if(button)button.click();else host.click();};
   candidates.push(['#'+CSS.escape(host.id),'.bk-modal',close,panel.querySelector('h2,h3,.bk-modal__title')?.textContent.trim()||'Formulario']);
  }
  for(const [selector,child,close,name] of candidates){const host=document.querySelector(selector),panel=child?host?.querySelector(child):host;if(!host||!panel)continue;
   const open=visible(host)&&(!host.classList.contains('bk-profile-drawer')||host.classList.contains('is-open'));
   const prior=states.get(host);
   if(open&&!prior){const origin=invoker||document.activeElement;panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');panel.setAttribute('aria-label',name);states.set(host,{panel,close,origin});const candidates=focusables(panel);if(!panel.contains(document.activeElement))(candidates.find(x=>x.matches('input,select,textarea'))||candidates[0])?.focus();}
   if(!open&&prior){states.delete(host);if(prior.origin?.isConnected)prior.origin.focus();}
  }
 }
 document.addEventListener('keydown',e=>{
  update();
  if(document.querySelector('dialog[open]'))return;
  const open=[...states.entries()].filter(([host])=>visible(host)).sort((a,b)=>(+getComputedStyle(a[0]).zIndex||0)-(+getComputedStyle(b[0]).zIndex||0)).pop();
  if(!open)return;const state=open[1];
  if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();if(typeof state.close==='function')state.close();else window[state.close]?.();return;}
  if(e.key==='Tab'){const items=focusables(state.panel),first=items[0],last=items.at(-1);if(!first){e.preventDefault();return;}if(e.shiftKey&&(!state.panel.contains(document.activeElement)||document.activeElement===first)){e.preventDefault();last.focus();}else if(!e.shiftKey&&(!state.panel.contains(document.activeElement)||document.activeElement===last)){e.preventDefault();first.focus();}}
 },true);
 document.addEventListener('animationend',update,true);
 function start(){let pending=false;new MutationObserver(()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;update();});}).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class','style']});update();}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
