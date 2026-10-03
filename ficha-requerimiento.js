// ─────────────────────────────────────────────────────────────────────────
// ficha-requerimiento.js · Pestaña "Requerimiento" de la ficha de contacto
// (la misma en las vistas Lista y Pipeline de Contactos).
//
//   1. Lo que busca: operaciones, tipos, zonas, presupuesto con moneda,
//      mínimos, superficies, características y financiamiento, "sólo con
//      comisión compartida" (routers/alertas.py).
//   2. Coincidencias en tu inventario, el de tu equipo y la Bolsa Broquer,
//      con envío al cliente por WhatsApp o correo (queda en la bitácora).
//   3. Encontrado en internet (el Buscador de propiedades de siempre).
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  function el(id) { return document.getElementById(id); }
  function esc(s) { return window.bkEsc ? window.bkEsc(s) : String(s == null ? '' : s); }
  function toast(t) { (typeof showToast === 'function' ? showToast : window.bkToast)(t); }
  function campo(lbl, ctrl, cls) { return '<div class="bk-field' + (cls ? ' ' + cls : '') + '"><label class="bk-label">' + lbl + '</label>' + ctrl + '</div>'; }
  function num(id, ph) { return '<input class="bk-input" type="number" min="0" inputmode="decimal" id="' + id + '" placeholder="' + (ph || '') + '"/>'; }
  var C = function () { return window.bkCat; };
  var COINC = [];

  function chips(name, items) {
    return '<div class="frq-chips">' + items.map(function (it) {
      return '<label class="frq-chip"><input type="checkbox" name="' + name + '" value="' + esc(it.key) + '"/><span>' + esc(it.label) + '</span></label>';
    }).join('') + '</div>';
  }
  function html() {
    var tipos = [];
    (C() ? C().data.tipos : []).forEach(function (g) { g.items.forEach(function (t) { tipos.push(t); }); });
    return '<p class="bk-prosa">Lo que busca este contacto. Broquer lo cruza primero con tu inventario, el de tu equipo y la Bolsa, te avisa cuando entra algo nuevo y, aparte, el Buscador lo revisa en internet una vez al día.</p>' +
      '<form id="frq-form" onsubmit="return false">' +
      campo('Operación', chips('frq-op', C() ? C().data.operaciones : [])) +
      campo('Tipos de inmueble', '<div class="frq-scroll">' + chips('frq-tipo', tipos) + '</div>') +
      '<div class="bk-field-row">' +
        campo('Zonas (colonias o ciudades, separadas por coma)', '<input class="bk-input" id="frq-zonas" placeholder="Altozano, Tres Marías, Morelia"/>') +
        campo('Estado', '<input class="bk-input" id="frq-estado" placeholder="Michoacán"/>') +
      '</div><div class="bk-field-row is-three">' +
        campo('Precio desde', num('frq-pmin', '$')) + campo('Precio hasta', num('frq-pmax', '$')) +
        campo('Moneda', '<select class="bk-select" id="frq-moneda"><option>MXN</option><option>USD</option></select>') +
      '</div><div class="bk-field-row is-three">' +
        campo('Recámaras mín.', num('frq-rec')) + campo('Baños mín.', num('frq-ban')) + campo('Estacionamientos mín.', num('frq-est')) +
      '</div><div class="bk-field-row">' +
        campo('m² construcción', '<div class="frq-rango">' + num('frq-m2c-min', 'mín.') + num('frq-m2c-max', 'máx.') + '</div>') +
        campo('m² terreno', '<div class="frq-rango">' + num('frq-m2t-min', 'mín.') + num('frq-m2t-max', 'máx.') + '</div>') +
      '</div>' +
      '<details class="frq-det"><summary>Características y financiamiento</summary><div class="frq-scroll">' + (C() ? C().caractCheckboxes('frq-car', []) : '') + '</div></details>' +
      '<label class="frq-chip frq-chip--linea"><input type="checkbox" id="frq-comp"/><span>Sólo inmuebles con comisión compartida</span></label>' +
      campo('Notas', '<textarea class="bk-input" id="frq-notas" rows="2" placeholder="Cualquier otro detalle que ayude a encontrar lo que busca…"></textarea>') +
      '<div class="bk-acciones"><label class="bk-switch"><input type="checkbox" id="frq-activo" checked/><span class="bk-switch__track"></span> Alertas activas</label>' +
        '<button class="bk-btn bk-btn--sm" id="frq-guardar" type="button">Guardar requerimiento</button></div></form>' +
      '<div class="bk-bloque"><div class="bk-acciones"><h3 class="bk-acciones__t">Coincidencias en tu inventario y la Bolsa</h3>' +
        '<button class="bk-btn bk-btn--sm" id="frq-enviar" type="button" disabled>Enviar al cliente</button></div><div id="frq-coinc"></div></div>' +
      '<div class="bk-bloque" id="bp-resultados-bloque"><div class="bk-acciones"><h3 class="bk-acciones__t" id="bp-resultados-titulo">Encontrado en internet</h3>' +
        '<button class="bk-btn bk-btn--ghost bk-btn--sm" id="bp-buscar-ahora" type="button">Buscar ahora</button></div><div id="bp-resultados-feed"></div></div>';
  }

  var TAB = '<button class="bk-tab" id="f-tab-requerimiento" role="tab" aria-selected="false" aria-controls="f-pane-requerimiento" onclick="setDetTab(\'requerimiento\')">' +
    'Requerimiento <span class="bk-tab__n" id="f-n-requerimiento" hidden></span></button>';

  window.frqMontar = function () {
    var pane = el('f-pane-requerimiento');
    if (pane && pane.dataset.frq) return;
    if (!pane) {
      var tabT = el('f-tab-tareas'), paneT = el('f-pane-tareas');
      if (!tabT || !paneT) return;
      tabT.insertAdjacentHTML('afterend', TAB);
      paneT.insertAdjacentHTML('afterend', '<div id="f-pane-requerimiento" role="tabpanel" aria-labelledby="f-tab-requerimiento" hidden></div>');
      pane = el('f-pane-requerimiento');
      envolverSetDetTab();
    }
    pane.innerHTML = html();          // en la vista Pipeline reemplaza el formulario viejo
    pane.dataset.frq = '1';
    el('frq-guardar').onclick = guardar;
    el('bp-buscar-ahora').onclick = buscarInternet;
    el('frq-enviar').onclick = enviar;
    el('frq-coinc').addEventListener('change', function () { el('frq-enviar').disabled = !el('frq-coinc').querySelector('input:checked'); });
  };
  function envolverSetDetTab() {
    if (typeof setDetTab !== 'function' || setDetTab.__frq) return;
    var orig = setDetTab;
    setDetTab = function (tab) {
      var pane = el('f-pane-requerimiento'), btn = el('f-tab-requerimiento');
      if (tab === 'requerimiento') {
        ['info', 'bitacora', 'props', 'tareas'].forEach(function (t) {
          var p = el('f-pane-' + t), b = el('f-tab-' + t);
          if (p) p.hidden = true;
          if (b) { b.classList.remove('is-active'); b.setAttribute('aria-selected', 'false'); }
        });
        pane.hidden = false; btn.classList.add('is-active'); btn.setAttribute('aria-selected', 'true');
        try { detTabActual = 'requerimiento'; } catch (e) {}
        window.bpCargarRequerimiento();
        return;
      }
      if (pane) pane.hidden = true;
      if (btn) { btn.classList.remove('is-active'); btn.setAttribute('aria-selected', 'false'); }
      return orig.apply(this, arguments);
    };
    setDetTab.__frq = true;
  }

  function contactoId() { return (typeof detContacto !== 'undefined' && detContacto) ? detContacto.id : null; }
  function marcar(name, valores) {
    document.querySelectorAll('#frq-form input[name="' + name + '"]').forEach(function (c) { c.checked = (valores || []).indexOf(c.value) !== -1; });
  }
  function leidos(name) { return Array.prototype.map.call(document.querySelectorAll('#frq-form input[name="' + name + '"]:checked'), function (c) { return c.value; }); }
  function put(id, v) { var e = el(id); if (e) e.value = v == null ? '' : v; }
  function val(id) { return Number((el(id) || {}).value) || 0; }

  window.bpCargarRequerimiento = async function () {
    window.frqMontar();
    var cid = contactoId(); if (!cid) return;
    el('frq-coinc').innerHTML = '<div class="bk-cargando"></div>';
    try {
      var r = await window.bkApi('/alertas/requerimiento/' + encodeURIComponent(cid));
      marcar('frq-op', r.operaciones && r.operaciones.length ? r.operaciones : (r.operacion ? [r.operacion] : ['venta']));
      marcar('frq-tipo', r.tipos && r.tipos.length ? r.tipos : (r.tipo_inmueble ? [r.tipo_inmueble] : []));
      marcar('frq-car', r.caracteristicas || []);
      put('frq-zonas', (r.zonas && r.zonas.length ? r.zonas : [r.colonia, r.ciudad].filter(Boolean)).join(', '));
      put('frq-estado', r.estado); put('frq-moneda', r.moneda || 'MXN');
      put('frq-pmin', r.precio_min || ''); put('frq-pmax', r.precio_max || '');
      put('frq-rec', r.recamaras_min || ''); put('frq-ban', r.banos_min || ''); put('frq-est', r.estacionamientos_min || '');
      put('frq-m2c-min', r.m2_construccion_min || ''); put('frq-m2c-max', r.m2_construccion_max || '');
      put('frq-m2t-min', r.m2_terreno_min || ''); put('frq-m2t-max', r.m2_terreno_max || '');
      el('frq-comp').checked = !!r.solo_comision_compartida;
      put('frq-notas', r.notas);
      el('frq-activo').checked = r.activo !== false;
      if (r.id) await cargarCoincidencias(); else el('frq-coinc').innerHTML = '<div class="bk-vacio"><h3>Sin requerimiento todavía</h3><p>Llena lo que busca y guarda: aquí aparecerán los inmuebles que coinciden.</p></div>';
    } catch (e) {
      el('frq-coinc').innerHTML = '<div class="bk-vacio"><h3>No se pudo cargar</h3><p>' + esc(e.message) + '</p></div>';
    }
    cargarInternet();
  };

  async function guardar() {
    var cid = contactoId(); if (!cid) return;
    var b = el('frq-guardar'); b.disabled = true; b.textContent = 'Guardando…';
    var body = {
      activo: el('frq-activo').checked, operaciones: leidos('frq-op'), tipos: leidos('frq-tipo'),
      zonas: el('frq-zonas').value.split(',').map(function (s) { return s.trim(); }).filter(Boolean),
      estado: el('frq-estado').value.trim(), moneda: el('frq-moneda').value,
      precio_min: val('frq-pmin'), precio_max: val('frq-pmax'), recamaras_min: val('frq-rec'), banos_min: val('frq-ban'),
      estacionamientos_min: val('frq-est'), m2_construccion_min: val('frq-m2c-min'), m2_construccion_max: val('frq-m2c-max'),
      m2_terreno_min: val('frq-m2t-min'), m2_terreno_max: val('frq-m2t-max'), caracteristicas: leidos('frq-car'),
      solo_comision_compartida: el('frq-comp').checked, notas: el('frq-notas').value.trim(),
    };
    try {
      await window.bkApi('/alertas/requerimiento/' + encodeURIComponent(cid), { method: 'PUT', json: body });
      toast('Requerimiento guardado'); await cargarCoincidencias();
    } catch (e) { toast(e.message || 'No se pudo guardar'); }
    finally { b.disabled = false; b.textContent = 'Guardar requerimiento'; }
  }

  async function cargarCoincidencias() {
    var cid = contactoId(); if (!cid) return;
    var cont = el('frq-coinc');
    cont.innerHTML = '<div class="bk-cargando"></div>';
    var d = await window.bkApi('/alertas/coincidencias/' + encodeURIComponent(cid));
    COINC = d.coincidencias || [];
    if (typeof bkContador === 'function') bkContador('f-n-requerimiento', COINC.length);
    var ORIGEN = { propio: 'Tuyo', equipo: 'De tu equipo', bolsa: 'Bolsa Broquer' };
    cont.innerHTML = COINC.length ? COINC.map(function (p) {
      var op = (p.operaciones || [])[0];
      var precio = op && C() ? C().opLabel(op.tipo) + ' · ' + C().precioTexto(op) : '';
      return '<label class="frq-prop"><input type="checkbox" value="' + esc(p.id) + '"/>' +
        (p.foto ? '<img src="' + esc(p.foto) + '" alt="" loading="lazy"/>' : '<span class="frq-prop__sin"></span>') +
        '<span class="frq-prop__txt"><strong>' + esc(p.titulo || p.tipo) + '</strong><small>' + esc([p.tipo, p.colonia, p.ciudad].filter(Boolean).join(' · ')) + '</small>' +
        '<small>' + esc(precio) + '</small><span class="frq-badges"><span class="frq-badge">' + esc(ORIGEN[p.origen] || '') + (p.bolsa_comision ? ' · comparte ' + p.bolsa_comision + '%' : '') + '</span>' +
        (p.enviada_en ? '<span class="frq-badge frq-badge--ok">Enviado ' + esc(new Date(p.enviada_en).toLocaleDateString('es-MX')) + '</span>' : '') + '</span></span>' +
        '<a class="frq-ver" href="propiedades.html?id=' + encodeURIComponent(p.id) + '" target="_blank" onclick="event.stopPropagation()"' + (p.origen === 'bolsa' ? ' hidden' : '') + '>Ver</a></label>';
    }).join('') : '<div class="bk-vacio"><h3>Nada coincide por ahora</h3><p>Te avisaremos por la app en cuanto entre un inmueble que le quede.</p></div>';
    el('frq-enviar').disabled = true;
  }

  async function enviar() {
    var cid = contactoId(); if (!cid) return;
    var ids = Array.prototype.map.call(el('frq-coinc').querySelectorAll('input:checked'), function (c) { return c.value; });
    if (!ids.length) return;
    var prep;
    try { prep = await window.bkApi('/alertas/preparar', { method: 'POST', json: { contacto_id: cid, propiedad_ids: ids } }); }
    catch (e) { toast(e.message); return; }
    var ov = document.createElement('div');
    ov.className = 'bk-overlay bk-overlay--sheet crm-modal';
    ov.innerHTML = '<div class="bk-modal" role="dialog" aria-modal="true"><div class="bk-modal__head"><div class="bk-modal__title">Enviar ' + ids.length + ' inmueble(s)</div></div>' +
      '<div class="bk-modal__body"><textarea class="bk-input" id="frq-msg" rows="9">' + esc(prep.mensaje) + '</textarea>' +
      '<p class="crm-sub">' + (prep.conversacion_id && prep.ventana_24h ? 'Se manda por el WhatsApp de Broquer (la conversación sigue abierta).' :
        prep.conversacion_id ? 'Pasaron más de 24 h desde su último mensaje: se abre tu WhatsApp con el texto listo (o manda una plantilla aprobada desde WhatsApp de Broquer).' :
        'Se abre tu WhatsApp con el texto listo.') + '</p></div>' +
      '<div class="bk-modal__foot"><button class="bk-btn bk-btn--ghost" data-x>Cancelar</button>' +
      (prep.email ? '<button class="bk-btn" data-correo>Por correo</button>' : '') +
      (prep.telefono || prep.conversacion_id ? '<button class="bk-btn bk-btn--forest" data-wa>Por WhatsApp</button>' : '') + '</div></div>';
    document.body.appendChild(ov);
    requestAnimationFrame(function () { ov.classList.add('is-open'); });
    var cerrar = function () { ov.classList.remove('is-open'); setTimeout(function () { ov.remove(); }, 250); };
    ov.querySelector('[data-x]').onclick = cerrar;
    async function registrar(canal) {
      await window.bkApi('/alertas/registrar-envio', { method: 'POST', json: { contacto_id: cid, propiedad_ids: ids, canal: canal } });
      cerrar(); toast('Enviado y anotado en la bitácora'); cargarCoincidencias();
    }
    var bw = ov.querySelector('[data-wa]');
    if (bw) bw.onclick = async function () {
      var texto = ov.querySelector('#frq-msg').value;
      bw.disabled = true;
      try {
        if (prep.conversacion_id && prep.ventana_24h) {
          await window.bkApi('/whatsapp2/mensajes', { method: 'POST', json: { conversacion_id: prep.conversacion_id, texto: texto } });
        } else {
          var d = String(prep.telefono || '').replace(/\D/g, ''); if (d.length === 10) d = '52' + d;
          window.open('https://wa.me/' + d + '?text=' + encodeURIComponent(texto), '_blank');
        }
        await registrar('whatsapp');
      } catch (e) { bw.disabled = false; toast(e.message); }
    };
    var bc = ov.querySelector('[data-correo]');
    if (bc) bc.onclick = async function () {
      var texto = ov.querySelector('#frq-msg').value;
      bc.disabled = true;
      try {
        try { await window.bkApi('/correo/enviar', { method: 'POST', json: { para: prep.email, asunto: prep.asunto, cuerpo: texto } }); }
        catch (e) { location.href = 'mailto:' + prep.email + '?subject=' + encodeURIComponent(prep.asunto) + '&body=' + encodeURIComponent(texto); }
        await registrar('correo');
      } catch (e) { bc.disabled = false; toast(e.message); }
    };
  }

  // ── Encontrado en internet (Buscador de propiedades de siempre) ──
  function fechaHora(iso) { try { return new Date(iso).toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; } }
  function pintarInternet(resultados, ultima) {
    el('bp-resultados-titulo').textContent = 'Encontrado en internet' + (ultima ? ' · ' + fechaHora(ultima) : '');
    el('bp-resultados-feed').innerHTML = (resultados || []).length ? resultados.map(function (r) {
      var precio = r.precio ? ' · $' + Number(r.precio).toLocaleString('es-MX') + (r.precio_confirmado ? '' : ' (sin confirmar)') : '';
      return '<div class="bk-fila"><a class="bk-fila__cuerpo" href="' + esc(r.url) + '" target="_blank" rel="noopener noreferrer"><span class="bk-fila__t">' + esc(r.titulo || r.portal || 'Ver anuncio') + '</span>' +
        '<span class="bk-fila__d">' + esc(r.portal || '') + precio + '</span></a></div>';
    }).join('') : '<div class="bk-vacio"><p>Sin enlaces todavía. Presiona "Buscar ahora".</p></div>';
  }
  async function cargarInternet() {
    var cid = contactoId(); if (!cid) return;
    try {
      var d = await window.bkApi('/api/buscador/resultados/' + encodeURIComponent(cid));
      pintarInternet(d.resultados, (d.requerimiento || {}).ultima_busqueda_en);
    } catch (e) { pintarInternet([], null); }
  }
  async function buscarInternet() {
    var cid = contactoId(); if (!cid) return;
    var b = el('bp-buscar-ahora'); b.disabled = true; b.textContent = 'Buscando…';
    try { await window.bkApi('/api/buscador/escanear/' + encodeURIComponent(cid), { method: 'POST' }); await cargarInternet(); }
    catch (e) { toast(e.message); }
    finally { b.disabled = false; b.textContent = 'Buscar ahora'; }
  }
  // Compatibilidad con llamadas viejas desde la vista Pipeline.
  window.bpGuardarRequerimiento = guardar;
  window.bpBuscarAhora = buscarInternet;

  if (!document.getElementById('frq-css')) {
    var st = document.createElement('style'); st.id = 'frq-css';
    st.textContent = '.frq-chips{display:flex;flex-wrap:wrap;gap:6px}.frq-chip{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid var(--line-2);border-radius:var(--r-pill);font-size:var(--fs-sm);cursor:pointer;background:var(--bone)}' +
      '.frq-chip input{width:16px;height:16px;accent-color:var(--ink)}.frq-chip--linea{border:0;padding:6px 0;background:none}' +
      '.frq-scroll{max-height:200px;overflow-y:auto;border:1px solid var(--line);border-radius:var(--r);padding:8px;background:var(--paper)}' +
      '.frq-rango{display:grid;grid-template-columns:1fr 1fr;gap:6px}.frq-det{margin:8px 0}.frq-det summary{cursor:pointer;font-weight:600;font-size:var(--fs-sm);padding:6px 0}' +
      '.frq-prop{display:flex;gap:10px;align-items:center;padding:10px;border:1px solid var(--line);border-radius:var(--r);background:var(--bone);margin-bottom:8px;cursor:pointer}' +
      '.frq-prop input{width:18px;height:18px;accent-color:var(--ink);flex-shrink:0}.frq-prop img,.frq-prop__sin{width:64px;height:48px;object-fit:cover;border-radius:var(--r-sm);background:var(--paper-2);flex-shrink:0}' +
      '.frq-prop__txt{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}.frq-prop__txt small{color:var(--mute);font-size:var(--fs-xs)}' +
      '.frq-badges{display:flex;gap:4px;flex-wrap:wrap}.frq-badge{font-size:var(--fs-label-3);padding:1px 7px;border-radius:var(--r-pill);background:var(--paper-2)}.frq-badge--ok{background:var(--success-soft)}' +
      '.frq-ver{font-size:var(--fs-xs);font-weight:600;color:var(--ink)}' +
      '.bk-field input[type=checkbox]{width:auto;height:auto}';
    document.head.appendChild(st);
  }
})();
