/* Shared Spanish date picker. Original date inputs, ISO values, validation and
 * application input/change handlers remain the source of truth. No services. */
(() => {
  'use strict';
  if (window.__broquerDates || typeof HTMLDialogElement === 'undefined') return;
  window.__broquerDates = true;
  const fields = new Map();
  const format = new Intl.DateTimeFormat('es-MX', {day:'2-digit',month:'2-digit',year:'numeric'});
  const longFormat = new Intl.DateTimeFormat('es-MX', {dateStyle:'full'});
  const monthFormat = new Intl.DateTimeFormat('es-MX', {month:'long',year:'numeric'});
  const iso = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  function parse(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
    if (!match) return null;
    const d = new Date(+match[1], +match[2]-1, +match[3]);
    return iso(d) === value ? d : null;
  }
  let active, shown, opener;
  const dialog = document.createElement('dialog');
  dialog.className = 'ui-date-dialog'; dialog.lang = 'es-MX';
  dialog.setAttribute('aria-labelledby','ui-date-title');
  dialog.innerHTML = `<header><button type="button" data-date-prev aria-label="Mes anterior">‹</button><h2 id="ui-date-title"></h2><button type="button" data-date-next aria-label="Mes siguiente">›</button><button type="button" data-date-close aria-label="Cerrar calendario">×</button></header><div class="ui-date-week" aria-hidden="true">${['L','M','M','J','V','S','D'].map(d=>`<span>${d}</span>`).join('')}</div><div class="ui-date-days" role="group" aria-label="Días del mes"></div><footer><button type="button" data-date-clear>Borrar</button><button type="button" data-date-today>Hoy</button></footer>`;
  const grid = dialog.querySelector('.ui-date-days');
  const allowed = value => (!active.min || value >= active.min) && (!active.max || value <= active.max);
  function refresh(input) {
    const proxy = fields.get(input);
    if (!proxy) return;
    const date = parse(input.value), text = date ? format.format(date) : 'dd/mm/aaaa';
    if (proxy.textContent !== text) proxy.textContent = text;
    proxy.disabled = input.disabled;
    proxy.setAttribute('aria-readonly', String(input.readOnly));
    proxy.setAttribute('aria-required', String(input.required));
    proxy.setAttribute('aria-invalid', String(!input.validity.valid));
  }
  function select(value) {
    if (!active || active.disabled || active.readOnly || (value && !allowed(value))) return;
    active.value = value;
    active.dispatchEvent(new Event('input', {bubbles:true}));
    active.dispatchEvent(new Event('change', {bubbles:true}));
    refresh(active); dialog.close();
  }
  function draw(focusValue) {
    dialog.querySelector('h2').textContent = monthFormat.format(shown);
    grid.replaceChildren();
    const offset = (shown.getDay()+6)%7;
    for(let i=0;i<offset;i++) grid.append(document.createElement('span'));
    const count = new Date(shown.getFullYear(),shown.getMonth()+1,0).getDate();
    const today = iso(new Date());
    const preferred = focusValue || active.value || today;
    for(let day=1;day<=count;day++) {
      const date = new Date(shown.getFullYear(),shown.getMonth(),day), value = iso(date);
      const b = document.createElement('button'); b.type='button'; b.textContent=day;
      b.dataset.date=value; b.disabled=!allowed(value); b.tabIndex=value===preferred?0:-1;
      b.setAttribute('aria-label',longFormat.format(date));
      b.setAttribute('aria-pressed',String(value===active.value));
      if(value===today)b.setAttribute('aria-current','date');
      b.onclick=()=>select(value);
      b.onkeydown=e=>{
        let delta=({ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7})[e.key];
        if(e.key==='Home')delta=-((date.getDay()+6)%7);
        if(e.key==='End')delta=6-((date.getDay()+6)%7);
        if(delta===undefined)return;
        e.preventDefault(); const target=new Date(date);target.setDate(target.getDate()+delta);
        if(!allowed(iso(target)))return;
        shown=new Date(target.getFullYear(),target.getMonth(),1);draw(iso(target));
        grid.querySelector(`[data-date="${iso(target)}"]`)?.focus();
      };
      grid.append(b);
    }
    if(!grid.querySelector('button[tabindex="0"]:not(:disabled)')) {
      grid.querySelectorAll('button').forEach(b=>b.tabIndex=-1);
      const first=grid.querySelector('button:not(:disabled)');if(first)first.tabIndex=0;
    }
    dialog.querySelector('[data-date-today]').disabled=!allowed(today);
    dialog.querySelector('[data-date-clear]').disabled=active.required;
  }
  function open(input, proxy) {
    if(input.disabled || input.readOnly)return;
    active=input;opener=proxy;
    const date=parse(input.value)||parse(input.min)||new Date();shown=new Date(date.getFullYear(),date.getMonth(),1);
    draw();dialog.showModal();grid.querySelector('button[tabindex="0"]')?.focus();
  }
  dialog.querySelector('[data-date-prev]').onclick=()=>{shown.setMonth(shown.getMonth()-1);draw();};
  dialog.querySelector('[data-date-next]').onclick=()=>{shown.setMonth(shown.getMonth()+1);draw();};
  dialog.querySelector('[data-date-today]').onclick=()=>select(iso(new Date()));
  dialog.querySelector('[data-date-clear]').onclick=()=>select('');
  dialog.querySelector('[data-date-close]').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{opener?.isConnected&&opener.focus();active=null;});
  dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
  function enhance(root) {
    const inputs = root.matches?.('input[type=date]') ? [root] : root.querySelectorAll?.('input[type=date]') || [];
    for(const input of inputs) {
      if(fields.has(input)||input.closest('.ui-date-field'))continue;
      const wrapper=document.createElement('span');wrapper.className='ui-date-field';
      const proxy=document.createElement('button');proxy.type='button';proxy.className='ui-date-trigger';
      const label=input.labels?.[0]?.textContent.trim()||input.getAttribute('aria-label')||input.title||input.placeholder||'Fecha';
      proxy.setAttribute('aria-label',label);proxy.setAttribute('aria-haspopup','dialog');
      input.before(wrapper);wrapper.append(input,proxy);
      input.classList.add('ui-date-source'); input.tabIndex=-1;input.setAttribute('aria-hidden','true');
      fields.set(input,proxy);refresh(input);
      proxy.onclick=()=>open(input,proxy);
      proxy.onkeydown=e=>{if(e.key==='ArrowDown'){e.preventDefault();open(input,proxy);}};
      input.addEventListener('input',()=>refresh(input));input.addEventListener('change',()=>refresh(input));
      input.addEventListener('focus',()=>proxy.focus());
      input.addEventListener('invalid',()=>proxy.setAttribute('aria-invalid','true'));
    }
  }
  function start() {
    document.body.append(dialog);enhance(document.body);
    new MutationObserver(records=>{for(const r of records)for(const n of r.addedNodes)if(n.nodeType===1)enhance(n);}).observe(document.body,{subtree:true,childList:true});
    // Programmatic assignments do not emit change; keep the displayed date in sync.
    setInterval(()=>{for(const [input] of fields){if(!input.isConnected)fields.delete(input);else refresh(input);}},400);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
