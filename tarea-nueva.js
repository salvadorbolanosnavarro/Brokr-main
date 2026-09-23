// Broquer · Modal "Nueva tarea" compartido (Tareas y ficha de Clientes).
// Un solo formulario con TODAS las opciones de una tarea: fecha y hora,
// notas, asignado (empresas), categorías, contactos e inmuebles vinculados
// y archivos adjuntos. Así crear una tarea desde un cliente permite
// exactamente lo mismo que crearla desde el módulo de Tareas.
//
// Requiere (cargados antes de usarse): app-shell.js (window.brokrSb),
// ficha-comun.js (bkBuscadorContactos/bkBuscadorPropiedades),
// categorias.js (catCargar/catCrear/catVincular/catPintarPicker) e
// historial-adjuntos.js (haAgregarArchivos/haTomarAdjuntosListos…).
//
// Uso:
//   bkTareaNueva.abrir({
//     contactos: ['id-del-cliente'],   // vínculos ya puestos (opcional)
//     propiedades: [],                 // (opcional)
//     ctx: { orgId, esEmpresa, miembros, categorias, contactos, propiedades },
//                                      // datos que la página ya tenga (opcional;
//                                      // lo que falte se carga aquí)
//     onCreada(tarea, vinculos) {}     // tras crear y vincular todo
//   });

(function () {
  const API = 'https://api.broquer.app';
  const PREVIEW = 'tn-adj-preview';
  let ctx = null;          // { orgId, esEmpresa, miembros, categorias, contactos, propiedades }
  let pend = null;         // { contactos, propiedades, categorias }
  let opts = {};
  let buscC = null, buscP = null;
  let uidCache = null;

  const $ = (id) => document.getElementById(id);
  const e = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  function rest(path, method, body) {
    if (!window.brokrSb || !window.brokrSb.rest) {
      return Promise.reject(new Error('La app aún se está cargando. Intenta de nuevo en un segundo.'));
    }
    return window.brokrSb.rest(path, { method: method || 'GET', body: body || null });
  }

  async function uid() {
    if (uidCache) return uidCache;
    const sb = window.brokrSb;
    const tok = sb && await sb.ensureToken();
    if (!tok) return null;
    try {
      const r = await fetch(sb.url + '/auth/v1/user', { headers: { apikey: sb.key, Authorization: 'Bearer ' + tok } });
      if (!r.ok) return null;
      uidCache = (await r.json())?.id || null;
    } catch { uidCache = null; }
    return uidCache;
  }

  // Lo que la página no haya pasado se carga una sola vez y se reusa.
  async function asegurarCtx(dado) {
    ctx = Object.assign({}, ctx || {}, dado || {});
    const tareas = [];
    if (ctx.orgId === undefined) {
      tareas.push((async () => {
        ctx.orgId = null; ctx.esEmpresa = false; ctx.miembros = [];
        try {
          const tok = await window.brokrSb.ensureToken();
          if (!tok) return;
          const r = await fetch(API + '/org', { headers: { Authorization: 'Bearer ' + tok } });
          if (!r.ok) return;
          const org = await r.json();
          ctx.orgId = org.org_id || null;
          ctx.esEmpresa = org.es_empresa === true;
          if (ctx.esEmpresa) {
            const rm = await fetch(API + '/org/miembros', { headers: { Authorization: 'Bearer ' + tok } });
            if (rm.ok) ctx.miembros = ((await rm.json()).miembros || []).filter(m => m.activo);
          }
        } catch { /* sin org: modo individual */ }
      })());
    }
    if (!Array.isArray(ctx.contactos)) {
      tareas.push(rest('contactos?select=id,nombre,telefono,email&order=updated_at.desc&limit=1000')
        .then(r => { ctx.contactos = Array.isArray(r) ? r : []; })
        .catch(() => { ctx.contactos = []; }));
    }
    if (!Array.isArray(ctx.propiedades)) {
      tareas.push(rest('propiedades?select=id,titulo,clave_interna,colonia,ciudad,tipo&order=updated_at.desc&limit=1000')
        .then(r => { ctx.propiedades = Array.isArray(r) ? r : []; })
        .catch(() => { ctx.propiedades = []; }));
    }
    await Promise.all(tareas);
    if (!Array.isArray(ctx.categorias)) ctx.categorias = ctx.orgId ? await catCargar(ctx.orgId) : [];
    if (!Array.isArray(ctx.miembros)) ctx.miembros = [];
  }

  function inyectar() {
    if ($('tn-modal')) return;
    const st = document.createElement('style');
    st.textContent = `
#tn-modal { z-index: 300; }
#tn-modal .tn-chips { display:flex; flex-wrap:wrap; gap:var(--sp-2); margin:var(--sp-2) 0; }
#tn-modal .tke-chip { display:inline-flex; align-items:center; gap:6px; padding:4px 10px; border-radius:var(--r-pill);
  background:var(--paper-2); font-size:var(--fs-xs); font-weight:600; }
#tn-modal .tke-chip button { background:none; border:0; cursor:pointer; color:var(--mute); font-size:var(--fs-sm); line-height:1; padding:0; }
#tn-modal .tn-adj-row { display:flex; align-items:center; gap:var(--sp-3); margin:var(--sp-2) 0; }
#tn-modal .ha-preview { margin:var(--sp-2) 0 0; }`;
    document.head.appendChild(st);

    const buscador = (tipo, ph) => `
      <div class="bk-field-row">
        <div class="prop-buscador">
          <input type="text" class="bk-input" id="tn-${tipo}-buscar" placeholder="${ph}" autocomplete="off"/>
          <input type="hidden" id="tn-${tipo}-id"/>
          <div class="prop-sugerencias" id="tn-${tipo}-sug" hidden></div>
        </div>
        <button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" id="tn-${tipo}-agregar">Agregar</button>
      </div>`;

    const ov = document.createElement('div');
    ov.className = 'bk-overlay';
    ov.id = 'tn-modal';
    ov.innerHTML = `
  <div class="bk-modal" role="dialog" aria-modal="true" aria-labelledby="tn-titulo-lbl">
    <div class="bk-modal__head"><span class="bk-modal__title" id="tn-titulo-lbl">Nueva tarea</span></div>
    <div class="bk-modal__body">
      <div class="bk-field"><label class="bk-label" for="tn-titulo">Título</label><input class="bk-input" id="tn-titulo" placeholder="Ej. Llamar a Pedro para agendar visita"/></div>
      <div class="bk-field-row">
        <div class="bk-field"><label class="bk-label" for="tn-fecha">Fecha</label><input class="bk-input" type="date" id="tn-fecha"/></div>
        <div class="bk-field"><label class="bk-label" for="tn-hora">Hora</label><input class="bk-input" type="time" id="tn-hora"/></div>
      </div>
      <div class="bk-field"><label class="bk-label" for="tn-notas">Notas</label><textarea class="bk-textarea" id="tn-notas" rows="2"></textarea></div>

      <div class="bk-field" id="tn-asignado-wrap" hidden>
        <label class="bk-label" for="tn-asignado">Asignado a</label>
        <select class="bk-select" id="tn-asignado"><option value="">Sin asignar</option></select>
      </div>

      <div class="bk-divider"></div>
      <span class="bk-eyebrow">Categorías</span>
      <div class="tn-chips" id="tn-cat-chips"></div>
      <div class="bk-field-row">
        <select class="bk-select" id="tn-cat-sel"><option value="">Agregar categoría…</option></select>
        <button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" id="tn-cat-nueva">+ Nueva</button>
      </div>

      <div class="bk-divider"></div>
      <span class="bk-eyebrow">Contactos vinculados</span>
      <div class="tn-chips" id="tn-c-chips"></div>
      ${buscador('c', 'Buscar contacto…')}

      <div class="bk-divider"></div>
      <span class="bk-eyebrow">Inmuebles vinculados</span>
      <div class="tn-chips" id="tn-p-chips"></div>
      ${buscador('p', 'Buscar inmueble…')}

      <div class="bk-divider"></div>
      <span class="bk-eyebrow">Archivos adjuntos</span>
      <div class="tn-adj-row">
        <input type="file" id="tn-adj-input" multiple hidden/>
        <button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" id="tn-adj-btn">Adjuntar archivos</button>
        <span class="bk-hint" style="margin:0">Fotos, videos, PDF… hasta 25 MB c/u</span>
      </div>
      <div class="ha-preview" id="${PREVIEW}"></div>
    </div>
    <div class="bk-modal__foot">
      <button type="button" class="bk-btn bk-btn--ghost" id="tn-cancelar">Cancelar</button>
      <button type="button" class="bk-btn bk-btn--forest" id="tn-crear">Crear tarea</button>
    </div>
  </div>`;
    document.body.appendChild(ov);

    ov.addEventListener('click', (ev) => { if (ev.target === ov) cerrar(); });
    $('tn-cancelar').onclick = cerrar;
    $('tn-crear').onclick = crear;
    $('tn-titulo').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') crear(); });
    $('tn-cat-nueva').onclick = nuevaCategoria;
    $('tn-adj-input').accept = typeof HA_ACCEPT === 'string' ? HA_ACCEPT : '';
    $('tn-adj-btn').onclick = () => $('tn-adj-input').click();
    $('tn-adj-input').onchange = function () { haAgregarArchivos(this.files, PREVIEW); this.value = ''; };

    buscC = bkBuscadorContactos('tn-c-buscar', 'tn-c-id', 'tn-c-sug', 'No hay más contactos para agregar');
    buscP = bkBuscadorPropiedades('tn-p-buscar', 'tn-p-id', 'tn-p-sug', 'No hay más inmuebles para agregar');
    const dispC = () => ctx.contactos.filter(c => !pend.contactos.includes(String(c.id)));
    const dispP = () => ctx.propiedades.filter(p => !pend.propiedades.includes(String(p.id)));
    $('tn-c-buscar').addEventListener('input', () => buscC.onInput(dispC()));
    $('tn-c-buscar').addEventListener('focus', () => buscC.onInput(dispC()));
    $('tn-c-buscar').addEventListener('keydown', (ev) => { buscC.onKeydown(ev); if (ev.key === 'Enter') agregar('contactos', 'tn-c-id'); });
    $('tn-p-buscar').addEventListener('input', () => buscP.onInput(dispP()));
    $('tn-p-buscar').addEventListener('focus', () => buscP.onInput(dispP()));
    $('tn-p-buscar').addEventListener('keydown', (ev) => { buscP.onKeydown(ev); if (ev.key === 'Enter') agregar('propiedades', 'tn-p-id'); });
    $('tn-c-agregar').onclick = () => agregar('contactos', 'tn-c-id');
    $('tn-p-agregar').onclick = () => agregar('propiedades', 'tn-p-id');
    // Elegir una sugerencia la agrega de una vez (sin tener que picar "Agregar").
    document.addEventListener('click', (ev) => {
      if (!ov.classList.contains('is-open')) return;
      if (buscC.manejarClick(ev.target)) { agregar('contactos', 'tn-c-id'); return; }
      if (buscP.manejarClick(ev.target)) { agregar('propiedades', 'tn-p-id'); return; }
      buscC.cerrarSiClickAfuera(ev.target);
      buscP.cerrarSiClickAfuera(ev.target);
    });
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && ov.classList.contains('is-open')) { ev.stopPropagation(); cerrar(); }
    }, true);
  }

  function agregar(tipo, hiddenId) {
    const id = $(hiddenId).value;
    if (!id || pend[tipo].includes(String(id))) return;
    pend[tipo].push(String(id));
    pintar();
  }

  function nombreContacto(id) {
    const c = ctx.contactos.find(x => String(x.id) === String(id));
    return c ? (c.nombre || 'Sin nombre') : 'Contacto';
  }
  function nombrePropiedad(id) {
    const p = ctx.propiedades.find(x => String(x.id) === String(id));
    return p ? (p.clave_interna || p.titulo || 'Inmueble') : 'Inmueble';
  }

  function chips(elId, ids, nombre, tipo) {
    const el = $(elId);
    el.innerHTML = ids.length
      ? ids.map(id => `<span class="tke-chip">${e(nombre(id))}<button type="button" data-q="${e(id)}" title="Quitar" aria-label="Quitar">×</button></span>`).join('')
      : '<span class="bk-hint">Ninguno todavía.</span>';
    el.querySelectorAll('[data-q]').forEach(b => b.addEventListener('click', () => {
      pend[tipo] = pend[tipo].filter(x => x !== b.getAttribute('data-q'));
      pintar();
    }));
  }

  function pintar() {
    chips('tn-c-chips', pend.contactos, nombreContacto, 'contactos');
    chips('tn-p-chips', pend.propiedades, nombrePropiedad, 'propiedades');
    ['c', 'p'].forEach(t => { $('tn-' + t + '-buscar').value = ''; $('tn-' + t + '-id').value = ''; $('tn-' + t + '-sug').hidden = true; });
    catPintarPicker({
      chipsEl: $('tn-cat-chips'),
      selectEl: $('tn-cat-sel'),
      catalogo: ctx.categorias,
      seleccionadas: pend.categorias,
      onQuitar: (id) => { pend.categorias = pend.categorias.filter(x => x !== String(id)); pintar(); },
      onAgregar: (id) => { if (!pend.categorias.includes(String(id))) pend.categorias.push(String(id)); pintar(); },
    });
  }

  async function nuevaCategoria() {
    const nombre = prompt('Nombre de la nueva categoría:');
    if (!nombre || !nombre.trim()) return;
    const u = await uid();
    if (!u || !ctx.orgId) return;
    const cat = await catCrear(ctx.orgId, u, nombre);
    if (!cat) { alert('No se pudo crear la categoría.'); return; }
    if (!ctx.categorias.some(c => String(c.id) === String(cat.id))) ctx.categorias.push(cat);
    if (!pend.categorias.includes(String(cat.id))) pend.categorias.push(String(cat.id));
    pintar();
  }

  async function abrir(o) {
    opts = o || {};
    inyectar();
    const btn = $('tn-crear');
    btn.disabled = true;
    pend = {
      contactos: (opts.contactos || []).map(String),
      propiedades: (opts.propiedades || []).map(String),
      categorias: [],
    };
    $('tn-titulo').value = opts.titulo || '';
    $('tn-fecha').value = opts.fecha || '';
    $('tn-hora').value = opts.hora || '';
    $('tn-notas').value = '';
    haTomarAdjuntosListos(PREVIEW); // limpia lo que haya quedado de otra vez
    $('tn-modal').classList.add('is-open');
    setTimeout(() => $('tn-titulo').focus(), 0);
    await asegurarCtx(opts.ctx);
    const mostrar = ctx.esEmpresa && ctx.miembros.length > 0;
    $('tn-asignado-wrap').hidden = !mostrar;
    if (mostrar) {
      $('tn-asignado').innerHTML = '<option value="">Sin asignar</option>' +
        ctx.miembros.map(m => `<option value="${e(m.user_id)}">${e(m.nombre || m.email)}</option>`).join('');
    }
    pintar();
    btn.disabled = false;
  }

  function cerrar() {
    const ov = $('tn-modal');
    if (ov) ov.classList.remove('is-open');
  }

  async function crear() {
    const titulo = $('tn-titulo').value.trim();
    if (!titulo) { alert('El título es obligatorio.'); $('tn-titulo').focus(); return; }
    if (haHaySubiendoPendiente(PREVIEW)) { alert('Espera a que terminen de subirse los archivos.'); return; }
    const u = await uid();
    if (!u) { alert('Tu sesión expiró. Vuelve a iniciar sesión.'); return; }
    const fecha = $('tn-fecha').value;
    const hora = $('tn-hora').value || '12:00';
    // Se leen sin vaciar la previsualización: si el POST falla, el
    // usuario no pierde lo que ya subió.
    const adjuntos = haAdjuntosListos(PREVIEW);
    const payload = {
      user_id: u,
      org_id: ctx.orgId || null,
      titulo,
      // Construir con Date (hora LOCAL del navegador) y toISOString() para el
      // instante UTC real; "fecha+T+hora" pelón Postgres lo tomaría como UTC.
      fecha_entrega: fecha ? new Date(fecha + 'T' + hora + ':00').toISOString() : null,
      notas: $('tn-notas').value.trim() || null,
      asignado_a: (ctx.esEmpresa && ctx.miembros.length) ? ($('tn-asignado').value || null) : null,
      // Columna "vieja" de un solo vínculo: la siguen leyendo Estadísticas y
      // los avisos de actividad; los vínculos completos van en las tablas puente.
      contacto_id: pend.contactos[0] || null,
      propiedad_id: pend.propiedades[0] || null,
    };
    if (adjuntos.length) payload.adjuntos = adjuntos;

    const btn = $('tn-crear');
    const prev = btn.textContent;
    btn.disabled = true; btn.textContent = 'Creando…';
    try {
      let rows;
      try {
        rows = await rest('tareas', 'POST', payload);
      } catch (err) {
        // Si aún no se corre migracion-tareas-adjuntos.sql la columna no
        // existe: se crea la tarea igual y se avisa que los archivos no se guardaron.
        if (!payload.adjuntos || !/adjuntos/i.test(String(err && err.message))) throw err;
        delete payload.adjuntos;
        rows = await rest('tareas', 'POST', payload);
        alert('La tarea se creó, pero los archivos no se pudieron guardar todavía (falta activar los adjuntos de tareas en la base de datos).');
      }
      const nueva = Array.isArray(rows) ? rows[0] : rows;
      if (!nueva || !nueva.id) throw new Error('Respuesta inesperada del servidor.');
      const tid = String(nueva.id);
      let fallidos = 0;
      const vinc = { contactos: [], propiedades: [], categorias: [] };
      for (const cid of pend.contactos) {
        try { await rest('tareas_contactos', 'POST', { user_id: u, tarea_id: tid, contacto_id: cid }); vinc.contactos.push(cid); }
        catch { fallidos++; }
      }
      for (const pid of pend.propiedades) {
        try { await rest('tareas_propiedades', 'POST', { user_id: u, tarea_id: tid, propiedad_id: pid }); vinc.propiedades.push(pid); }
        catch { fallidos++; }
      }
      for (const cat of pend.categorias) {
        if (await catVincular('tareas_categorias', 'tarea_id', tid, cat)) vinc.categorias.push(cat);
        else fallidos++;
      }
      haTomarAdjuntosListos(PREVIEW);
      cerrar();
      if (typeof opts.onCreada === 'function') {
        await opts.onCreada(nueva, vinc, fallidos);
      }
    } catch (err) {
      alert('No se pudo crear la tarea.\n\n' + ((err && err.message) || err));
    } finally {
      btn.disabled = false; btn.textContent = prev;
    }
  }

  window.bkTareaNueva = { abrir, cerrar };
})();
