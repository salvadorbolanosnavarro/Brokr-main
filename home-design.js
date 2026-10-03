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
    document.getElementById('design-expand').textContent = expanded ? 'Ver herramientas principales ↑' : 'Explorar todas las herramientas →';
  }
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
  document.getElementById('design-date').textContent = new Intl.DateTimeFormat('es-MX', { weekday:'long', day:'numeric', month:'long', timeZone:'America/Mexico_City' }).format(new Date());
  document.getElementById('design-assistant').onclick = () => document.querySelector('.bk-shaark-fab')?.click();
  window.addEventListener('brokr-shell-ready', async e => {
    const profile = e.detail?.profile;
    const name = profile?.fullName || profile?.profile?.nombre || '';
    document.getElementById('design-name').textContent = name ? ', ' + name.trim().split(/\s+/)[0] : '';
    // Respect the platform's disabled modules in the launcher as well as the shell.
    const disabled = new Set(profile?.profile?.modulos_desactivados || []);
    const keys = {'propiedades.html':'props','tareas.html':'tareas','clientes.html':'clientes','contactos.html':'contactos','facebook-ads.html':'facebook-ads','image-cleaner.html':'image-cleaner'};
    cards.forEach(card => { card.dataset.disabled = String(disabled.has(keys[card.dataset.tool] || card.dataset.tool.replace('.html',''))); });
    render();
    const box = document.getElementById('design-next-task');
    try {
      const rows = await window.brokrSb.rest('tareas?select=id,titulo,fecha_entrega,propiedad_id&completada=eq.false&order=fecha_entrega.asc.nullslast&limit=1');
      const next = rows?.[0];
      let property;
      if (next?.propiedad_id) {
        try { property = (await window.brokrSb.rest('propiedades?id=eq.' + encodeURIComponent(next.propiedad_id) + '&select=id,titulo,fotos,colonia,ciudad'))?.[0]; } catch (_) {}
      }
      box.replaceChildren();
      if (property) {
        let photos = property.fotos;
        try { if (typeof photos === 'string') photos = JSON.parse(photos); } catch (_) { photos = []; }
        const source = Array.isArray(photos) ? (typeof photos[0] === 'string' ? photos[0] : photos[0]?.url) : '';
        if (source && /^https?:\/\//.test(source)) {
          const image = document.createElement('img'); image.src = source; image.alt = property.titulo || 'Inmueble de la próxima tarea'; image.className = 'design-next-photo'; box.append(image);
        }
        const location = document.createElement('p'); location.className = 'design-next-location'; location.textContent = [property.colonia, property.ciudad].filter(Boolean).join(', '); box.append(location);
      }
      const title = document.createElement('h3');
      title.textContent = rows?.[0]?.titulo || 'Tu agenda está al día';
      const date = document.createElement('p');
      date.textContent = rows?.[0]?.fecha_entrega ? new Intl.DateTimeFormat('es-MX',{dateStyle:'medium',timeStyle:'short',timeZone:'America/Mexico_City'}).format(new Date(rows[0].fecha_entrega)) : 'Organiza tu siguiente paso.';
      const link = document.createElement('a'); link.href = 'tareas.html'; link.textContent = 'Ver agenda ↗';
      box.append(title,date,link);
    } catch (_) {
      const message = document.createElement('p'); message.textContent = 'No se pudo consultar tu próxima tarea. Abre la agenda para volver a intentar.'; box.replaceChildren(message); const link = document.createElement('a'); link.href = 'tareas.html'; link.textContent = 'Abrir agenda ↗'; box.append(link);
    }
  });
  render();
})();
