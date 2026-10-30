/* Review page only: no application auth, services, persistence or customer data. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id), openers=new WeakMap();
 function open(dialog,opener=document.activeElement){openers.set(dialog,opener);dialog.showModal();}
 function toast(message){$('ui-toast')?.remove();const n=document.createElement('div');n.id='ui-toast';n.className='ui-notice ui-toast';n.setAttribute('role','status');n.textContent=message;document.body.append(n);setTimeout(()=>n.remove(),4000);}
 document.addEventListener('click',e=>{const trigger=e.target.closest('[data-open]');if(trigger)open($(trigger.dataset.open),trigger);const close=e.target.closest('[data-close]');if(close)close.closest('dialog').close();const notice=e.target.closest('[data-toast]');if(notice)toast(notice.dataset.toast);});
 document.querySelectorAll('dialog').forEach(d=>{d.addEventListener('close',()=>openers.get(d)?.focus());d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}});});
 $('sample-form').addEventListener('submit',e=>{e.preventDefault();$('modal-sample').close();toast('Registro de muestra guardado. No se enviaron datos.');});
 $('confirm-delete').onclick=()=>{$('delete-sample').close();toast('Confirmación de muestra: no se eliminó ningún dato.');};
 $('add-phone').onclick=()=>{const label=document.createElement('label');label.className='ui-field';const text=document.createElement('span');text.className='ui-label';text.textContent='Otro teléfono';const input=document.createElement('input');input.type='tel';input.className='ui-input';label.append(text,input);$('extra-phones').append(label);input.focus();};
 document.querySelector('[data-reset-filters]').onclick=()=>{document.querySelectorAll('#filters input').forEach(e=>{if(e.type==='checkbox')e.checked=false;else e.value='';});document.querySelectorAll('#filters select').forEach(e=>e.selectedIndex=0);};
 const tabs=[...document.querySelectorAll('[role=tab]')];
 function selectTab(tab){tabs.forEach(t=>{const selected=t===tab;t.setAttribute('aria-selected',selected);t.tabIndex=selected?0:-1;$(t.getAttribute('aria-controls')).hidden=!selected;});}
 tabs.forEach((t,i)=>{t.onclick=()=>selectTab(t);t.onkeydown=e=>{let n;if(e.key==='ArrowRight')n=(i+1)%tabs.length;if(e.key==='ArrowLeft')n=(i+tabs.length-1)%tabs.length;if(e.key==='Home')n=0;if(e.key==='End')n=tabs.length-1;if(n!==undefined){e.preventDefault();selectTab(tabs[n]);tabs[n].focus();}};});
 const radios=[...document.querySelectorAll('[role=radio]')];
 function chooseRadio(r){radios.forEach(b=>{b.setAttribute('aria-checked',b===r);b.tabIndex=b===r?0:-1;});$('segment-result').textContent=r.textContent==='Lista'?'Vista de lista seleccionada.':'Vista de pipeline seleccionada.';}
 radios.forEach((r,i)=>{r.onclick=()=>chooseRadio(r);r.onkeydown=e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();const n=radios[(i+1)%radios.length];chooseRadio(n);n.focus();}};});
 $('chat-form').onsubmit=e=>{e.preventDefault();const text=$('chat-input').value.trim();if(!text)return;const message=document.createElement('p');message.className='ui-chat-message';message.textContent='Tú: '+text;const response=document.createElement('p');response.className='ui-chat-message';response.textContent='Respuesta de muestra: así se verá una conversación con Broq. Esta página no utiliza IA ni envía mensajes.';$('chat-messages').append(message,response);$('chat-input').value='';$('chat-input').focus();};
 const calendar=$('calendar-sample'),field=$('sample-date'),stored=$('sample-date-iso');
 let shown=new Date();shown=new Date(shown.getFullYear(),shown.getMonth(),1);
 const iso=d=>[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
 function draw(focusDate){
  $('calendar-month').textContent=new Intl.DateTimeFormat('es-MX',{month:'long',year:'numeric'}).format(shown);
  const grid=$('calendar-days');grid.replaceChildren();const offset=(shown.getDay()+6)%7,count=new Date(shown.getFullYear(),shown.getMonth()+1,0).getDate();
  for(let i=0;i<offset;i++){const blank=document.createElement('span');blank.setAttribute('aria-hidden','true');grid.append(blank);}
  const today=iso(new Date()),focus=focusDate||stored.value||(shown.getFullYear()===new Date().getFullYear()&&shown.getMonth()===new Date().getMonth()?today:iso(shown));
  for(let day=1;day<=count;day++){
   const date=new Date(shown.getFullYear(),shown.getMonth(),day),value=iso(date),b=document.createElement('button');b.type='button';b.className='ui-btn ui-btn--sm';b.dataset.date=value;b.textContent=day;b.setAttribute('aria-label',new Intl.DateTimeFormat('es-MX',{dateStyle:'full'}).format(date));b.setAttribute('aria-pressed',stored.value===value);if(value===today)b.setAttribute('aria-current','date');b.tabIndex=value===focus?0:-1;
   b.onclick=()=>setDate(date);
   b.onkeydown=e=>{let delta=({'ArrowLeft':-1,'ArrowRight':1,'ArrowUp':-7,'ArrowDown':7})[e.key];if(e.key==='Home')delta=-((date.getDay()+6)%7);if(e.key==='End')delta=6-((date.getDay()+6)%7);if(delta!==undefined){e.preventDefault();const target=new Date(date);target.setDate(target.getDate()+delta);shown=new Date(target.getFullYear(),target.getMonth(),1);draw(iso(target));grid.querySelector('[data-date="'+iso(target)+'"]').focus();}};
   grid.append(b);
  }
  if(!grid.querySelector('[tabindex="0"]'))grid.querySelector('button').tabIndex=0;
 }
 function setDate(date){stored.value=iso(date);field.value=new Intl.DateTimeFormat('es-MX',{day:'2-digit',month:'2-digit',year:'numeric'}).format(date);stored.dispatchEvent(new Event('change',{bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}));calendar.close();}
 function openCalendar(){if(stored.value){const [y,m]=stored.value.split('-').map(Number);shown=new Date(y,m-1,1);}draw();open(calendar,field);$('calendar-days').querySelector('[tabindex="0"]').focus();}
 field.onclick=openCalendar;field.onkeydown=e=>{if(['Enter',' ','ArrowDown'].includes(e.key)){e.preventDefault();openCalendar();}};
 $('calendar-prev').onclick=()=>{shown.setMonth(shown.getMonth()-1);draw();};$('calendar-next').onclick=()=>{shown.setMonth(shown.getMonth()+1);draw();};$('calendar-today').onclick=()=>setDate(new Date());$('calendar-clear').onclick=()=>{stored.value='';field.value='';field.dispatchEvent(new Event('change',{bubbles:true}));calendar.close();};
})();
