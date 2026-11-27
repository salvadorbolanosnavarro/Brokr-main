/* Presentation and personal preferences; business data uses the existing platform. */
(() => {
  const cards = [...document.querySelectorAll('.design-tool')];
  let favorites = new Set();
  try { favorites = new Set(JSON.parse(localStorage.getItem('broquer_tool_favorites') || '[]')); } catch (_) {}
  let onlyFavorites = false, expanded = false;
  const search = document.getElementById('design-tool-search');
  function render() {
    const query = search.value.trim().toLocaleLowerCase('es');
    let count = 0;
    cards.forEach(card => {
      const favorite = favorites.has(card.dataset.tool);
      const button = card.querySelector('.design-favorite');
      button.setAttribute('aria-pressed', String(favorite));
      button.textContent = favorite ? '★' : '☆';
      card.hidden = card.dataset.disabled === 'true' || (onlyFavorites && !favorite) || (!query && !expanded && !onlyFavorites && card.dataset.extra === 'true') || !card.textContent.toLocaleLowerCase('es').includes(query);
      if (!card.hidden) count++;
    });
    document.getElementById('design-tools-empty').hidden = count > 0;
    document.getElementById('design-fav-count').textContent = favorites.size;
    document.getElementById('design-all').setAttribute('aria-pressed', String(!onlyFavorites));
    document.getElementById('design-favorites').setAttribute('aria-pressed', String(onlyFavorites));
    document.getElementById('design-expand').textContent = expanded ? 'Ver herramientas principales' : 'Explorar todas las herramientas →';
  }
  cards.forEach(card => card.addEventListener('click', e => {
    // composedPath survives the star being re-rendered during this same click.
    if (e.composedPath().some(el => el.matches && el.matches('button,a'))) return;
    card.querySelector('.design-tool-link')?.click();
  }));
  cards.forEach(card => card.querySelector('.design-favorite').addEventListener('click', () => {
    const key = card.dataset.tool;
    favorites.has(key) ? favorites.delete(key) : favorites.add(key);
    try { localStorage.setItem('broquer_tool_favorites', JSON.stringify([...favorites])); } catch (_) {}
    render();
  }));
  document.getElementById('design-all').onclick = () => { onlyFavorites = false; render(); };
  document.getElementById('design-favorites').onclick = () => { onlyFavorites = true; render(); };
  document.getElementById('design-expand').onclick = () => { expanded = !expanded; render(); };
  document.getElementById('design-customize').onclick = () => { expanded = true; onlyFavorites = false; render(); cards[0]?.querySelector('button').focus(); };
  search.addEventListener('input', render);
  document.getElementById('design-date').textContent = new Intl.DateTimeFormat('es-MX', { weekday:'long', day:'numeric', month:'long' }).format(new Date());
  document.getElementById('design-assistant').onclick = () => document.querySelector('.bk-shaark-fab')?.click();
  // Greeting by the person's local time.
  function greeting(date = new Date()) {
    const h = date.getHours();
    return h >= 5 && h < 12 ? 'Buenos días' : h >= 12 && h < 19 ? 'Buenas tardes' : 'Buenas noches';
  }
  const hello = document.getElementById('design-hello');
  hello.textContent = greeting();
  setInterval(() => { hello.textContent = greeting(); }, 60000);
  // First name of the person, never the company. Without one, no name.
  const COMPANY = /\b(s\.?\s?a\.?|s\.?\s?c\.?|de\s+c\.?\s?v\.?|sapi|tech|inmobiliaria|bienes\s+ra[ií]ces|realty|group|grupo|corp|consult|properties|propiedades|asesores|desarrollos|capital|holding)\b/i;
  function firstName(profile) {
    const meta = profile?.user?.user_metadata || {};
    const org = (profile?.org?.organizacion?.nombre || profile?.org?.org?.nombre || '').trim().toLocaleLowerCase('es');
    const candidates = [meta.nombre, meta.first_name, meta.given_name, meta.full_name, meta.name, profile?.profile?.nombre];
    for (const raw of candidates) {
      const value = String(raw || '').trim();
      if (!value || value.includes('@') || COMPANY.test(value)) continue;
      if (org && value.toLocaleLowerCase('es') === org) continue;
      const first = value.split(/\s+/)[0];
      if (!/^[\p{L}'’-]{2,}$/u.test(first)) continue;
      return window.cpProperName ? window.cpProperName(first) : first;
    }
    return '';
  }
  const dateTime = new Intl.DateTimeFormat('es-MX', { weekday:'short', day:'numeric', month:'short', hour:'numeric', minute:'2-digit' });
  window.addEventListener('brokr-shell-ready', async e => {
    const profile = e.detail?.profile;
    const name = firstName(profile);
    document.getElementById('design-name').textContent = name ? ', ' + name : '';
    // Respect the platform's disabled modules in the launcher as well as the shell.
    const disabled = new Set(profile?.profile?.modulos_desactivados || []);
    const keys = {'propiedades.html':'props','tareas.html':'tareas','clientes.html':'clientes','contactos.html':'contactos','facebook-ads.html':'facebook-ads','image-cleaner.html':'image-cleaner'};
    cards.forEach(card => { card.dataset.disabled = String(disabled.has(keys[card.dataset.tool] || card.dataset.tool.replace('.html',''))); });
    render();
    const box = document.getElementById('design-next-task');
    const section = box.closest('.design-next');
    const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
    try {
      // Pending = not completed (false or empty), same rule as the Agenda.
      const rows = await window.brokrSb.rest('tareas?select=id,titulo,fecha_entrega,contacto_id,propiedad_id,completada&completada=not.is.true&order=fecha_entrega.asc.nullslast&limit=1000') || [];
      const now = Date.now();
      const pending = rows.filter(t => !t.completada);
      const overdue = pending.filter(t => t.fecha_entrega && new Date(t.fecha_entrega).getTime() < now);
      const next = pending.find(t => !t.fecha_entrega || new Date(t.fecha_entrega).getTime() >= now);
      box.replaceChildren();
      if (next) {
        const link = el('a', 'design-next-item'); link.href = 'tareas.html?tarea=' + encodeURIComponent(next.id);
        link.append(el('strong', 'design-next-title', next.titulo || 'Tarea sin título'));
        const meta = [next.fecha_entrega ? dateTime.format(new Date(next.fecha_entrega)) : 'Sin fecha'];
        let vinculo = '';
        try {
          if (next.contacto_id) vinculo = (await window.brokrSb.rest('contactos?id=eq.' + encodeURIComponent(next.contacto_id) + '&select=nombre'))?.[0]?.nombre || '';
          else if (next.propiedad_id) vinculo = (await window.brokrSb.rest('propiedades?id=eq.' + encodeURIComponent(next.propiedad_id) + '&select=titulo'))?.[0]?.titulo || '';
        } catch (_) {}
        if (vinculo) meta.push(window.cpProperName && vinculo === vinculo.toLocaleUpperCase('es') ? window.cpProperName(vinculo) : vinculo);
        link.append(el('span', 'design-next-meta', meta.join(' · ')));
        box.append(link);
      } else {
        box.append(el('p', 'design-next-empty', 'Sin pendientes'));
      }
      if (overdue.length) {
        const late = el('a', 'design-next-overdue', overdue.length === 1 ? '1 vencida' : overdue.length + ' vencidas');
        late.href = 'tareas.html?filtro=vencidas';
        box.append(late);
      }
      const all = el('a', 'design-next-all', 'Ver agenda →'); all.href = 'tareas.html'; box.append(all);
    } catch (_) {
      box.replaceChildren(el('p', 'design-next-empty', 'No se pudo consultar tu agenda.'));
      const link = el('a', 'design-next-all', 'Abrir agenda →'); link.href = 'tareas.html'; box.append(link);
    }
    section?.removeAttribute('aria-busy');
  });
  render();
})();
