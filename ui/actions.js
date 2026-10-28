/* Compatibility adapter: existing handlers/IDs stay intact while old action
 * classes map to the approved component. List rows/media are not actions. */
(() => {
 'use strict';if(window.__broquerActions)return;window.__broquerActions=true;
 const structural=/\b(?:bz-item|bx-conv|wac-number|ln-poster|faq-q|mig-opt|doc-opt|tool-card|num-card|mv-poster|video-poster)\b/;
 const textStyle=/bk-design-assistant|bk-design-account|design-favorite|design-expand|bk-file-close|w2-numeros-link/;
 const tabStyle=/\b(?:bk-tab|ftab|tk-tab|crm-tab|tab-btn)\b/;
 const segmentStyle=/bk-seg__btn|toggle-btn|sexo-btn|sexo-opt|bx-filter|w2-chip|ms-tab|tipo-tab|period-btn/;
 const visual=['background','background-color','background-image','color','border','border-color','border-radius','box-shadow','font-size','font-family','font-weight','height','min-height','padding','line-height'];
 function enhance(e){
  if(e.closest('.ui-date-dialog,.ui-date-field')||structural.test(e.className||''))return;
  if(!e.dataset.uiKind){
   const text=(e.textContent||'').trim(), classes=e.className||'', key=classes+' '+e.id;
   let kind='secondary';
   if(tabStyle.test(classes))kind='tab';
   else if(segmentStyle.test(classes)||/^(Este mes|Mes pasado|Trimestre|Este año|Semana|Mes|Todo|Todas|Favoritas \d+)$/.test(text))kind='segment';
   else if(textStyle.test(key)||/^(Personalizar|Explorar todas las herramientas)/.test(text))kind='text';
   else if(/danger|delete|btn-del\b|borrar|eliminar/i.test(key)||/^(Eliminar|Borrar)/i.test(text))kind='danger';
   else if(/px-add|crmAgregarFila/.test(key+' '+(e.getAttribute('onclick')||'')))kind='secondary';
   else if(/primary|--forest|btn-new|add-btn|submit|save-btn|btn-calc|ai-btn|btn-clean|btn-analizar|reg-submit|contact-btn/.test(key)||/^(Nuevo |Nueva |Guardar|Crear|Generar|Calcular|Continuar|Entrar|Buscar$|Registrar|Conectar|Subir|Enviar|Verificar|Firmar|Publicar)/i.test(text))kind='primary';
   e.dataset.uiKind=kind;
   e.dataset.uiSize=/--sm|icon|close|cerrar|\btk-(?:edit|x|check)\b|prop-check|design-favorite/.test(key)||kind==='text'?'small':'normal';
  }
  for(const prop of visual)if(e.style.getPropertyValue(prop))e.style.removeProperty(prop);
  if(['segment','tab'].includes(e.dataset.uiKind)){
   const selected=e.matches('.active,.is-active,.is-on,.selected,.bk-chip--forest,[aria-selected=true]');
   e.dataset.uiSelected=String(selected);e.setAttribute(e.getAttribute('role')==='tab'?'aria-selected':'aria-pressed',String(selected));
  }
 }
 function field(input){
  if(input.matches('input[type=checkbox],input[type=radio],input[type=hidden],input[type=file],input[type=range],input[type=color],input[type=button],input[type=submit],input[type=date],.ui-date-source'))return;
  if(!input.dataset.uiField){
   let container=input.parentElement;
   if(container?.className&&/search|buscador|busqueda/i.test(container.className)&&container.querySelectorAll('input').length===1){container.dataset.uiSearch='true';input.dataset.uiField='search';}
   else input.dataset.uiField=input.tagName==='TEXTAREA'?'textarea':input.tagName==='SELECT'?'select':'input';
   for(const prop of visual)if(input.style.getPropertyValue(prop))input.style.removeProperty(prop);
  }
 }
 function scan(root){if(root.matches?.('input,select,textarea'))field(root);root.querySelectorAll?.('input,select,textarea').forEach(field);if(root.matches?.('button,a.bk-btn,a[class*="btn"]'))enhance(root);root.querySelectorAll?.('button,a.bk-btn,a[class*="btn"]').forEach(enhance);}
 document.addEventListener('keydown',event=>{
  const button=event.target.closest('[data-ui-kind=tab],[data-ui-kind=segment]');if(!button||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  const group=button.closest('.bk-tabs,.tabs,.tk-tabs,.bk-seg,.crm-tabs,.ms-tabs,.sexo-row,.toggle-group,.w2-chips,.bx-filters')||button.parentElement;
  const items=[...group.querySelectorAll(`[data-ui-kind=${button.dataset.uiKind}]`)].filter(e=>!e.disabled&&e.getClientRects().length);
  if(items.length<2)return;event.preventDefault();const index=items.indexOf(button),next=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowRight'?1:items.length-1))%items.length;
  items[next].click();if(items[next].isConnected)items[next].focus();
 });
 function start(){scan(document.body);new MutationObserver(records=>{for(const r of records){if(r.type==='attributes')scan(r.target);else for(const n of r.addedNodes)if(n.nodeType===1)scan(n);}}).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class','style']});}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
