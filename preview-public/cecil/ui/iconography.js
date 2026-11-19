/* Presentation only: never changes form values, stored records or event handlers. */
(() => {
  const paths={
    star:'m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z',
    check:'m5 12 4 4L19 6',close:'m6 6 12 12M6 18 18 6',
    alert:'m12 3 10 18H2ZM12 9v5m0 3v.1',
    home:'m3 10 9-7 9 7M5 9v12h5v-7h4v7h5V9',
    user:'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-3a8 8 0 0 1 16 0v3',
    calendar:'M5 5h14v16H5ZM8 3v4m8-4v4M5 10h14m-10 5h1m4 0h1',
    mail:'M3 5h18v14H3Zm0 1 9 7 9-7',
    phone:'M7 3H3v4c0 8 6 14 14 14h4v-4l-5-2-2 3a14 14 0 0 1-8-8l3-2Z',
    document:'M5 3h9l5 5v13H5Zm9 0v5h5M8 12h8m-8 4h6',
    chat:'M3 4h18v13H9l-6 4Zm5 6h8',
    pin:'M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0ZM14 10a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z',
    money:'M12 2v20m5-16H9a4 4 0 0 0 0 8h6a4 4 0 0 1 0 8H6',
    tag:'M3 3h8l10 10-8 8L3 11Zm4 4h.1',
    pause:'M8 5v14m8-14v14',
    clock:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 7v5l3 2',
    status:'M21 12a9 9 0 1 1-9-9m4 1 3 3-7 7-3-3',
    spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',
    arrow:'M4 12h16m-6-6 6 6-6 6'
  };
  function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('class','mc-icon');svg.setAttribute('aria-hidden','true');const p=document.createElementNS(svg.namespaceURI,'path');p.setAttribute('d',paths[name]||paths.spark);svg.append(p);return svg;}
  const glyph=/(?![©®™])[\p{Extended_Pictographic}\p{Regional_Indicator}★☆✓✔✕✖✗]+(?:[\uFE0E\uFE0F\u200D\p{Emoji_Modifier}\p{Extended_Pictographic}])*|[0-9#*]\uFE0F?\u20E3/gu;
  const names=g=>/[★☆⭐🌟]/u.test(g)?'star':/[✓✔✅☑]/u.test(g)?'check':/[✕✖✗❌❎]/u.test(g)?'close':/[🏠🏡🏢]/u.test(g)?'home':/[📅🗓]/u.test(g)?'calendar':/[📧✉📨]/u.test(g)?'mail':/[📞☎📱]/u.test(g)?'phone':/[👤👥🙋]/u.test(g)?'user':/[📍📌]/u.test(g)?'pin':/[💰💵💲]/u.test(g)?'money':/[💬🗨]/u.test(g)?'chat':/[⚠🚨]/u.test(g)?'alert':/[📄📃📋📝]/u.test(g)?'document':'spark';
  const labels={star:'Favorito',check:'Completado',close:'Cerrar',spark:'Información',alert:'Aviso',home:'Inmueble',calendar:'Fecha',mail:'Correo',phone:'Teléfono',user:'Persona',pin:'Ubicación',money:'Importe',chat:'Mensaje',document:'Documento'};
  const metadata='.est-chip,.role-badge,.tag-chip,.rb-badge,.wac-badge,.w2-tag,.w2-cal-badge,.auto-badge,.opt-badge,.isr-badge,.stat-pill,.pd-tag,.bk-pill--dato,.prop-card .badge,.count-badge,.ai-badge,.mk-tag,.mach-tag';
  function enhance(root){
    if(!root||root.nodeType!==1||root.closest('script,style,svg,textarea,[contenteditable=true]'))return;
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
    for(const node of nodes){const parent=node.parentElement;if(!parent||parent.closest('script,style,svg,textarea,[contenteditable=true]'))continue;glyph.lastIndex=0;if(!glyph.test(node.data))continue;glyph.lastIndex=0;
      if(parent.closest('option')){node.data=node.data.replace(/[★☆]+/gu,m=>`${m.length} de 5`).replace(glyph,'');continue;}
      const fragment=document.createDocumentFragment();let start=0;
      for(const match of node.data.matchAll(glyph)){fragment.append(node.data.slice(start,match.index));const name=names(match[0]);const svg=icon(name);const control=parent.closest('button,a');if(control&&!control.hasAttribute('aria-label')&&!control.textContent.replace(glyph,'').trim())control.setAttribute('aria-label',labels[name]);fragment.append(svg);start=match.index+match[0].length;}fragment.append(node.data.slice(start));node.replaceWith(fragment);
    }
    for(const el of [ ...(root.matches(metadata)?[root]:[]),...root.querySelectorAll(metadata)]){el.classList.add('mc-label');if(!el.querySelector('svg')&&el.textContent.trim()){const text=el.textContent.toLocaleLowerCase('es');const name=/suspend|inactiv|no.activ|paus|archivad/.test(text)?'pause':/pendiente|proceso|reserv|borrador/.test(text)?'clock':/error|rechaz|vencid|advert/.test(text)?'alert':/activ|vendid|rentad|complet|firmad|aprobad/.test(text)?'status':/role/.test(el.className)?'user':'tag';el.prepend(icon(name));}}
    for(const el of root.querySelectorAll('[placeholder],[title],[aria-label]'))for(const attr of ['placeholder','title','aria-label'])if(el.hasAttribute(attr))el.setAttribute(attr,el.getAttribute(attr).replace(glyph,'').trim());
  }
  function start(){enhance(document.body);const pending=new Set();let scheduled=false;new MutationObserver(records=>{for(const r of records){const el=r.type==='characterData'?r.target.parentElement:r.target;if(el?.nodeType===1&&!el.closest('svg'))pending.add(el);}if(!scheduled&&pending.size){scheduled=true;requestAnimationFrame(()=>{scheduled=false;const roots=[...pending];pending.clear();for(const root of roots)enhance(root);});}}).observe(document.body,{childList:true,subtree:true,characterData:true});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
