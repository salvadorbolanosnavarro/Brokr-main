// ─────────────────────────────────────────────────────────────────────────
// crm-plus.js · Contactos completo (se monta sobre contactos.html = vista
// Lista y clientes.html = vista Pipeline).
//
//   · Un solo módulo "Contactos" con selector Lista / Pipeline y acceso a
//     Ajustes de CRM (sólo admin).
//   · Etapas, tipos y fuentes salen del catálogo de la organización
//     (routers/crm.py); la etapa se guarda por clave, así renombrar no rompe.
//   · Ficha: varios teléfonos y correos con tipo, puesto y redes sociales;
//     "Sexo" opcional dentro de "Datos para contratos".
//   · Posibles duplicados (mismo teléfono a 10 dígitos o mismo correo) con
//     herramienta para fusionar.
//   · Filtros avanzados y acciones en lote (asignar, etapa, etiquetas, CSV).
//
// Engancha funciones globales que ambas páginas comparten (cargar,
// upsertRemoto, abrirModal, abrirDetalle, contactosFiltrados, cargarEtapas,
// renderActual…) sin reescribirlas.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var esc = window.bkEsc;
  var api = window.bkApi;
  var toast = function (t) { (typeof showToast === 'function' ? showToast : window.bkToast)(t); };
  var VISTA = document.body.getAttribute('data-app') === 'clientes' ? 'pipeline' : 'lista';
  var CAT = { etapas: [], tipos: [], fuentes: [], es_admin: false };
  var listo = false;

  function g(id) { return document.getElementById(id); }
  function norm(t) { return String(t || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(); }
  function tel10(v) { var d = String(v || '').replace(/\D/g, ''); if (d.length > 10) d = d.slice(-10); return d.length === 10 ? d : ''; }
  window.crmTel10 = tel10;

  // ════════════════════════════════════════════════════════════════════
  // 1. Selector de vista + Ajustes
  // ════════════════════════════════════════════════════════════════════
  function montarVistas() {
    var row = document.querySelector('.page-head__row');
    if (!row || g('crm-vistas')) return;
    var h1 = row.querySelector('h1'); if (h1) h1.textContent = 'Contactos';
    var qs = location.search || '';
    var div = document.createElement('div');
    div.className = 'crm-vistas'; div.id = 'crm-vistas';
    div.innerHTML = '<nav class="bk-seg" aria-label="Vista">' +
      '<a class="bk-seg__btn' + (VISTA === 'lista' ? ' is-active' : '') + '" href="contactos.html' + qs + '"' + (VISTA === 'lista' ? ' aria-current="page"' : '') + '>' +
        '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>Lista</a>' +
      '<a class="bk-seg__btn' + (VISTA === 'pipeline' ? ' is-active' : '') + '" href="clientes.html' + qs + '"' + (VISTA === 'pipeline' ? ' aria-current="page"' : '') + '>' +
        '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M4 5h4v14H4zM10 5h4v9h-4zM16 5h4v6h-4z"/></svg>Pipeline</a>' +
      '</nav><a class="crm-gear" href="alertas.html">' +
        '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"/></svg>Alertas de búsqueda</a>' +
      '<a class="crm-gear" id="crm-gear" href="crm-ajustes.html" hidden>' +
        '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M10.3 4.3c.4-1.7 3-1.7 3.4 0a1.7 1.7 0 002.6 1.1c1.5-.9 3.3.8 2.4 2.4a1.7 1.7 0 001 2.5c1.8.4 1.8 3 0 3.4a1.7 1.7 0 00-1 2.6c.9 1.5-.9 3.3-2.4 2.4a1.7 1.7 0 00-2.6 1c-.4 1.8-3 1.8-3.4 0a1.7 1.7 0 00-2.5-1c-1.6.9-3.3-.9-2.4-2.4a1.7 1.7 0 00-1.1-2.6c-1.7-.4-1.7-3 0-3.4a1.7 1.7 0 001.1-2.5c-.9-1.6.8-3.3 2.4-2.4a1.7 1.7 0 002.5-1.1z"/><circle cx="12" cy="12" r="3"/></svg>Ajustes de CRM</a>';
    row.parentNode.insertBefore(div, row.nextSibling);
    document.querySelectorAll('.bk-volver span').forEach(function (s) { if (/Directorio|Clientes/.test(s.textContent)) s.textContent = 'Contactos'; });
    var sub = document.querySelector('.cl-sub'); if (sub) sub.textContent = 'Vista Pipeline: tus clientes potenciales por etapa. Arrastra para cambiarlos de etapa.';
  }

  // ════════════════════════════════════════════════════════════════════
  // 2. Catálogos de la organización
  // ════════════════════════════════════════════════════════════════════
  async function cargarCatalogos() {
    try { CAT = await api('/crm/catalogos'); } catch (e) { return false; }
    var gear = g('crm-gear'); if (gear) gear.hidden = !CAT.es_admin;
    aplicarCatalogos();
    return true;
  }
  function aplicarCatalogos() {
    if (CAT.etapas && CAT.etapas.length && typeof ETAPAS !== 'undefined') {
      ETAPAS = CAT.etapas.map(function (e) { return { clave: e.clave, nombre: e.nombre, color: e.color || 'var(--etapa-activo)' }; });
    }
    if (typeof ROLES !== 'undefined') {
      (CAT.tipos || []).forEach(function (t) {
        var corto = t.nombre.split(' / ')[0];
        if (!ROLES[t.clave]) ROLES[t.clave] = { lbl: corto, cls: 'rb-otro' };
        else ROLES[t.clave].lbl = corto;
      });
    }
    var sel = g('m-tipo');
    if (sel && CAT.tipos && CAT.tipos.length) {
      var v = sel.value;
      sel.innerHTML = CAT.tipos.map(function (t) { return '<option value="' + esc(t.clave) + '">' + esc(t.nombre) + '</option>'; }).join('');
      if (v) sel.value = v;
    }
    var dl = g('fuentes-dl');
    if (dl && CAT.fuentes) dl.innerHTML = CAT.fuentes.map(function (f) { return '<option value="' + esc(f.nombre) + '"></option>'; }).join('');
  }
  // La etapa se toma del catálogo por clave (no por nombre en minúsculas).
  if (typeof cargarEtapas === 'function') {
    var _cargarEtapasOrig = cargarEtapas;
    cargarEtapas = async function () {
      if (CAT.etapas && CAT.etapas.length) { aplicarCatalogos(); return; }
      try {
        var rows = await restGet('pipeline_etapas?select=clave,nombre,orden,color&order=orden.asc');
        var vistas = {};
        var lista = (rows || []).map(function (r) { return { clave: r.clave || String(r.nombre || '').toLowerCase().trim(), nombre: r.nombre, color: r.color || 'var(--etapa-activo)' }; })
          .filter(function (e) { if (!e.clave || vistas[e.clave]) return false; vistas[e.clave] = 1; return true; });
        if (lista.length) { ETAPAS = lista; return; }
      } catch (e) { /* columna clave aún sin migrar */ }
      return _cargarEtapasOrig();
    };
  }

  // ════════════════════════════════════════════════════════════════════
  // 3. Formulario: teléfonos, correos, puesto, redes, sexo opcional
  // ════════════════════════════════════════════════════════════════════
  var TIPOS_TEL = [['celular', 'Celular'], ['oficina', 'Oficina'], ['casa', 'Casa'], ['otro', 'Otro']];
  var TIPOS_MAIL = [['personal', 'Personal'], ['trabajo', 'Trabajo'], ['otro', 'Otro']];
  var REDES = [['facebook', 'Facebook'], ['instagram', 'Instagram'], ['linkedin', 'LinkedIn'], ['tiktok', 'TikTok'], ['x', 'X / Twitter'], ['web', 'Sitio web']];
  function filaMulti(kind, val, tipo) {
    var opts = (kind === 'tel' ? TIPOS_TEL : TIPOS_MAIL).map(function (o) { return '<option value="' + o[0] + '"' + (o[0] === tipo ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('');
    return '<div class="crm-multi__fila"><input type="' + (kind === 'tel' ? 'tel' : 'email') + '" class="crm-mv" value="' + esc(val || '') + '" placeholder="' + (kind === 'tel' ? '443 123 4567' : 'correo@ejemplo.com') + '"/>' +
      '<select class="crm-mt">' + opts + '</select><button type="button" class="crm-btn-x" aria-label="Quitar" onclick="this.parentNode.remove()">×</button></div>';
  }
  window.crmAgregarFila = function (kind) { g(kind === 'tel' ? 'crm-tels' : 'crm-mails').insertAdjacentHTML('beforeend', filaMulti(kind, '', kind === 'tel' ? 'celular' : 'personal')); };

  function montarFormulario() {
    var email = g('m-email'); if (!email || g('crm-extra-form')) return;
    var cont = email.closest('.f');
    var html = '<div id="crm-extra-form">' +
      '<div class="f"><label>Otros teléfonos</label><div class="crm-multi" id="crm-tels"></div>' +
        '<button type="button" class="bk-btn bk-btn--quiet bk-btn--sm" onclick="crmAgregarFila(\'tel\')">+ Agregar teléfono</button></div>' +
      '<div class="f"><label>Otros correos</label><div class="crm-multi" id="crm-mails"></div>' +
        '<button type="button" class="bk-btn bk-btn--quiet bk-btn--sm" onclick="crmAgregarFila(\'mail\')">+ Agregar correo</button></div>' +
      '<div class="f"><label>Puesto</label><input id="crm-puesto" type="text" placeholder="Ej. Director de compras"/></div>' +
      '<details class="crm-sec"><summary>Redes sociales</summary><div class="frow">' +
        REDES.map(function (r) { return '<div class="f"><label>' + r[1] + '</label><input id="crm-red-' + r[0] + '" type="text" placeholder="usuario o liga"/></div>'; }).join('') +
      '</div></details></div>';
    cont.insertAdjacentHTML('afterend', html);
    // "Sexo" sale de los datos básicos y se vuelve opcional dentro de
    // "Datos para contratos" (abajo del domicilio).
    var sexoRow = document.querySelector('.sexo-row');
    if (sexoRow) {
      var campo = sexoRow.closest('.f');
      if (!sexoRow.querySelector('[data-s=""]')) {
        sexoRow.insertAdjacentHTML('beforeend', '<button class="sexo-opt" data-s="" onclick="setSexo(\'\',this)">Sin especificar</button>');
      }
      var mpio = g('m-mpio');
      var ancla = (mpio && mpio.closest('.frow')) || null;
      if (campo && ancla) {
        var det = document.createElement('details');
        det.className = 'crm-sec'; det.id = 'crm-contratos';
        det.innerHTML = '<summary>Datos para contratos (opcional)</summary>';
        det.appendChild(campo);
        ancla.parentNode.insertBefore(det, ancla.nextSibling);
      }
    }
  }
  function llenarFormulario(c) {
    if (!g('crm-tels')) return;
    g('crm-tels').innerHTML = ((c && c.telefonos) || []).map(function (t) { return filaMulti('tel', t.numero, t.tipo); }).join('');
    g('crm-mails').innerHTML = ((c && c.correos) || []).map(function (t) { return filaMulti('mail', t.correo, t.tipo); }).join('');
    g('crm-puesto').value = (c && c.puesto) || '';
    REDES.forEach(function (r) { g('crm-red-' + r[0]).value = ((c && c.redes) || {})[r[0]] || ''; });
    if (!c) {
      // Contacto nuevo: sexo sin especificar y sin municipio inventado.
      if (typeof setSexo === 'function') { var b = document.querySelector('.sexo-opt[data-s=""]'); if (b) setSexo('', b); }
      var mp = g('m-mpio'); if (mp && /MORELIA/.test(mp.value)) mp.value = '';
    }
  }
  function leerFormulario() {
    var leer = function (id, campo) {
      return Array.prototype.map.call(document.querySelectorAll('#' + id + ' .crm-multi__fila'), function (f) {
        var o = { tipo: f.querySelector('.crm-mt').value }; o[campo] = f.querySelector('.crm-mv').value.trim(); return o;
      }).filter(function (o) { return o[campo]; });
    };
    var redes = {};
    REDES.forEach(function (r) { var v = g('crm-red-' + r[0]).value.trim(); if (v) redes[r[0]] = v; });
    return { telefonos: leer('crm-tels', 'numero'), correos: leer('crm-mails', 'correo'), puesto: g('crm-puesto').value.trim() || null, redes: redes };
  }
  async function fuenteId(nombre) {
    if (!nombre) return null;
    var f = (CAT.fuentes || []).find(function (x) { return x.nombre_norm === norm(nombre) || norm(x.nombre) === norm(nombre); });
    if (f) return f;
    try { f = await api('/crm/fuentes', { method: 'POST', json: { nombre: nombre } }); CAT.fuentes.push(f); return f; } catch (e) { return null; }
  }
  if (typeof abrirModal === 'function') {
    var _abrirModalOrig = abrirModal;
    abrirModal = async function (id) {
      montarFormulario(); aplicarCatalogos();
      var p = _abrirModalOrig.apply(this, arguments);
      var c = id ? cargar().find(function (x) { return x.id === id; }) : null;
      llenarFormulario(c);
      if (c && c.tipo && g('m-tipo')) g('m-tipo').value = c.tipo;
      return p;
    };
  }
  if (typeof upsertRemoto === 'function') {
    var _upsertOrig = upsertRemoto;
    upsertRemoto = async function (contacto) {
      var modalAbierto = g('modal-ov') && g('modal-ov').classList.contains('open') && g('crm-tels');
      var extra = {};
      if (modalAbierto && contacto && (!editandoId || contacto.id === editandoId)) {
        extra = leerFormulario();
        var f = await fuenteId(contacto.fuente);
        if (f) { extra.fuente_id = f.id; extra.fuente = f.nombre; }
        if (contacto.sexo === '') extra.sexo = null;
      }
      try { return await _upsertOrig(Object.assign({}, contacto, extra)); }
      catch (e) {
        // Columnas de la fase 3 aún sin migrar: guardar lo de siempre.
        if (/PGRST204|Could not find/.test(String(e.message))) return _upsertOrig(contacto);
        throw e;
      }
    };
  }

  // ════════════════════════════════════════════════════════════════════
  // 4. Duplicados
  // ════════════════════════════════════════════════════════════════════
  var DUP = {};   // id → [ids de posibles duplicados]
  function calcularDuplicados() {
    DUP = {};
    var porClave = {};
    cargar().forEach(function (c) {
      var claves = [];
      [c.telefono, c.wa, c.whatsapp].concat((c.telefonos || []).map(function (t) { return t.numero; }))
        .forEach(function (t) { var n = tel10(t); if (n) claves.push('t' + n); });
      [c.email].concat((c.correos || []).map(function (x) { return x.correo; }))
        .forEach(function (m) { m = String(m || '').trim().toLowerCase(); if (m && m.indexOf('@') > 0) claves.push('m' + m); });
      claves.filter(function (k, i) { return claves.indexOf(k) === i; }).forEach(function (k) { (porClave[k] = porClave[k] || []).push(String(c.id)); });
    });
    Object.keys(porClave).forEach(function (k) {
      var ids = porClave[k]; if (ids.length < 2) return;
      ids.forEach(function (id) {
        DUP[id] = DUP[id] || [];
        ids.forEach(function (o) { if (o !== id && DUP[id].indexOf(o) === -1) DUP[id].push(o); });
      });
    });
  }
  window.crmDuplicadosDe = function (id) { return DUP[String(id)] || []; };
  function nombreDe(id) { var c = cargar().find(function (x) { return String(x.id) === String(id); }); return c ? (c.nombre || 'Sin nombre') : id; }

  window.crmFusionar = function (a, b) {
    var ca = cargar().find(function (x) { return String(x.id) === String(a); });
    var cb = cargar().find(function (x) { return String(x.id) === String(b); });
    if (!ca || !cb) return;
    var linea = function (c) { return [c.telefono, c.email, c.fuente, c.created_at ? 'Alta ' + new Date(c.created_at).toLocaleDateString('es-MX') : ''].filter(Boolean).join(' · '); };
    var ov = document.createElement('div');
    ov.className = 'bk-overlay bk-overlay--sheet crm-modal';
    ov.innerHTML = '<div class="bk-modal" role="dialog" aria-modal="true"><div class="bk-modal__head"><div class="bk-modal__title">Fusionar contactos</div></div>' +
      '<div class="bk-modal__body"><p>¿Cuál se queda? Del otro se juntan notas, tareas, inmuebles ligados, conversaciones, etiquetas, teléfonos y correos; después se elimina.</p>' +
      '<div class="crm-dup-opc">' +
        '<label><input type="radio" name="crm-keep" value="' + esc(ca.id) + '" checked/><span><strong>' + esc(ca.nombre) + '</strong><small>' + esc(linea(ca)) + '</small></span></label>' +
        '<label><input type="radio" name="crm-keep" value="' + esc(cb.id) + '"/><span><strong>' + esc(cb.nombre) + '</strong><small>' + esc(linea(cb)) + '</small></span></label>' +
      '</div></div><div class="bk-modal__foot"><button class="bk-btn bk-btn--ghost" data-x>Cancelar</button><button class="bk-btn bk-btn--forest" data-ok>Fusionar</button></div></div>';
    document.body.appendChild(ov);
    requestAnimationFrame(function () { ov.classList.add('is-open'); });
    var cerrar = function () { ov.classList.remove('is-open'); setTimeout(function () { ov.remove(); }, 250); };
    ov.querySelector('[data-x]').onclick = cerrar;
    ov.addEventListener('click', function (e) { if (e.target === ov) cerrar(); });
    ov.querySelector('[data-ok]').onclick = async function () {
      var keep = ov.querySelector('input[name=crm-keep]:checked').value;
      var drop = keep === String(ca.id) ? String(cb.id) : String(ca.id);
      this.disabled = true;
      try {
        await api('/crm/contactos/fusionar', { method: 'POST', json: { conservar_id: keep, eliminar_id: drop } });
        cerrar(); toast('Contactos fusionados');
        if (typeof cerrarDetalle === 'function') try { cerrarDetalle(); } catch (e) {}
        await cargarRemoto(); calcularDuplicados(); renderActual();
        if (typeof abrirDetalle === 'function') abrirDetalle(keep);
      } catch (e) { this.disabled = false; toast(e.message); }
    };
  };

  // ════════════════════════════════════════════════════════════════════
  // 5. Ficha: datos extra, aviso de duplicado y Requerimiento
  // ════════════════════════════════════════════════════════════════════
  function linkRed(k, v) {
    if (/^https?:\/\//i.test(v)) return v;
    var u = String(v).replace(/^@/, '');
    return { facebook: 'https://facebook.com/', instagram: 'https://instagram.com/', linkedin: 'https://linkedin.com/in/', tiktok: 'https://tiktok.com/@', x: 'https://x.com/', web: 'https://' }[k] + u;
  }
  function pintarFichaExtra(c) {
    var info = g('f-pane-info'); if (!info || !c) return;
    var viejo = g('crm-ficha-extra'); if (viejo) viejo.remove();
    var vb = g('crm-dup-banner'); if (vb) vb.remove();
    var dups = DUP[String(c.id)] || [];
    if (dups.length) {
      var tabs = (g('f-tab-info') && g('f-tab-info').closest('.bk-tabs')) || info;
      tabs.insertAdjacentHTML(tabs === info ? 'afterbegin' : 'beforebegin', '<div class="crm-dup-banner" id="crm-dup-banner"><span>Posible duplicado de <strong>' +
        dups.slice(0, 3).map(function (d) { return esc(nombreDe(d)); }).join(', ') + '</strong> (mismo teléfono o correo).</span>' +
        '<button class="bk-btn bk-btn--sm" onclick="crmFusionar(\'' + esc(c.id) + '\',\'' + esc(dups[0]) + '\')">Fusionar</button></div>');
    }
    var filas = [];
    (c.telefonos || []).forEach(function (t) { filas.push('<div><span class="crm-k">' + esc(t.tipo || 'Teléfono') + '</span> <a href="tel:' + esc(t.numero) + '">' + esc(t.numero) + '</a></div>'); });
    (c.correos || []).forEach(function (t) { filas.push('<div><span class="crm-k">' + esc(t.tipo || 'Correo') + '</span> <a href="mailto:' + esc(t.correo) + '">' + esc(t.correo) + '</a></div>'); });
    if (c.puesto) filas.push('<div><span class="crm-k">Puesto</span> ' + esc(c.puesto) + '</div>');
    Object.keys(c.redes || {}).forEach(function (k) {
      var lbl = (REDES.find(function (r) { return r[0] === k; }) || [k, k])[1];
      filas.push('<div><span class="crm-k">' + esc(lbl) + '</span> <a href="' + esc(linkRed(k, c.redes[k])) + '" target="_blank" rel="noopener">' + esc(c.redes[k]) + '</a></div>');
    });
    if (filas.length) {
      info.insertAdjacentHTML('beforeend', '<div class="bk-bloque" id="crm-ficha-extra"><h3 class="bk-bloque__t">Más datos de contacto</h3><div class="crm-extra">' + filas.join('') + '</div></div>');
    }
  }
  if (typeof abrirDetalle === 'function') {
    var _abrirDetalleOrig = abrirDetalle;
    abrirDetalle = function (id) {
      var r = _abrirDetalleOrig.apply(this, arguments);
      var c = cargar().find(function (x) { return String(x.id) === String(id); });
      pintarFichaExtra(c);
      if (window.frqMontar) window.frqMontar();
      return r;
    };
  }

  // ════════════════════════════════════════════════════════════════════
  // 6. Filtros avanzados
  // ════════════════════════════════════════════════════════════════════
  var F = {};
  var EXTRA = { tareas: null, actividad: null, req: null };  // datos perezosos
  async function cargarExtrasFiltros() {
    if (EXTRA.tareas) return;
    EXTRA.tareas = {}; EXTRA.actividad = {}; EXTRA.req = {};
    try {
      var tc = await restGet('tareas_contactos?select=contacto_id,tarea_id');
      var tareas = await restGet('tareas?select=id,completada&completada=eq.false');
      var abiertas = {}; (tareas || []).forEach(function (t) { abiertas[t.id] = 1; });
      (tc || []).forEach(function (l) { if (abiertas[l.tarea_id]) EXTRA.tareas[l.contacto_id] = (EXTRA.tareas[l.contacto_id] || 0) + 1; });
    } catch (e) {}
    try {
      var acts = await restGet('actividades?select=contacto_id,created_at&contacto_id=not.is.null&order=created_at.desc&limit=5000');
      (acts || []).forEach(function (a) { if (!EXTRA.actividad[a.contacto_id]) EXTRA.actividad[a.contacto_id] = a.created_at; });
    } catch (e) {}
    try {
      var reqs = await restGet('requerimientos_busqueda?select=*');
      (reqs || []).forEach(function (r) { EXTRA.req[r.contacto_id] = r; });
    } catch (e) {}
  }
  function vacio(v) { return v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length); }
  function enRango(iso, d, h) {
    if (!d && !h) return true; if (!iso) return false;
    var t = new Date(iso).getTime();
    if (d && t < new Date(d + 'T00:00:00').getTime()) return false;
    if (h && t > new Date(h + 'T23:59:59').getTime()) return false;
    return true;
  }
  function pasa(c) {
    if (F.dups && !(DUP[String(c.id)] || []).length) return false;
    if (!vacio(F.etapas) && F.etapas.indexOf(String(c.estatus || 'nuevo').toLowerCase()) === -1) return false;
    if (!vacio(F.tipos) && F.tipos.indexOf(c.tipo || 'otro') === -1) return false;
    if (!vacio(F.fuentes) && F.fuentes.indexOf(norm(c.fuente)) === -1) return false;
    if (!vacio(F.tags) && !F.tags.some(function (t) { return (c.etiquetas || []).indexOf(t) !== -1; })) return false;
    if (!vacio(F.prob) && F.prob.indexOf(c.probabilidad || '') === -1) return false;
    if (!enRango(c.created_at, F.creadoD, F.creadoH)) return false;
    if (!enRango(c.etapa_cambiada_en, F.etapaD, F.etapaH)) return false;
    if (F.tareas === 'con' && !EXTRA.tareas[c.id]) return false;
    if (F.tareas === 'sin' && EXTRA.tareas[c.id]) return false;
    if (F.actN) {
      var ult = EXTRA.actividad[c.id] || c.updated_at;
      var dentro = ult && (Date.now() - new Date(ult).getTime()) <= Number(F.actN) * 86400000;
      if (F.actModo === 'con' && !dentro) return false;
      if (F.actModo !== 'con' && dentro) return false;
    }
    if (F.intOp || F.intTipo || F.intZona || F.intPmin || F.intPmax) {
      var r = EXTRA.req[c.id] || {};
      if (F.intOp && (r.operacion || '') !== F.intOp && !(r.operaciones || []).includes(F.intOp)) return false;
      if (F.intTipo && (r.tipo_inmueble || '') !== F.intTipo && !(r.tipos || []).includes(F.intTipo)) return false;
      if (F.intZona) {
        var z = norm(F.intZona);
        var zonas = [r.colonia, r.ciudad, r.estado].concat(r.zonas || []).map(norm).join(' | ');
        if (zonas.indexOf(z) === -1) return false;
      }
      var pmin = Number(r.precio_min) || 0, pmax = Number(r.precio_max) || 0;
      if (F.intPmin && pmax && pmax < Number(F.intPmin)) return false;
      if (F.intPmax && pmin && pmin > Number(F.intPmax)) return false;
      if ((F.intPmin || F.intPmax) && !pmin && !pmax) return false;
    }
    return true;
  }
  if (typeof contactosFiltrados === 'function') {
    var _filtrOrig = contactosFiltrados;
    contactosFiltrados = function () { return _filtrOrig.apply(this, arguments).filter(pasa); };
  }
  function contar() { return Object.keys(F).filter(function (k) { return !vacio(F[k]) && k !== 'actModo'; }).length; }
  function pintarBoton() {
    var b = g('crm-fil-btn'); if (!b) return;
    var n = contar();
    b.querySelector('.crm-badge').textContent = n; b.querySelector('.crm-badge').hidden = !n;
  }
  function montarFiltros() {
    var fila = document.querySelector('.filters-row'); if (!fila || g('crm-fil-btn')) return;
    fila.insertAdjacentHTML('beforeend', '<button type="button" class="bk-btn bk-btn--ghost bk-btn--sm crm-filtros-btn" id="crm-fil-btn" onclick="crmAbrirFiltros()">' +
      'Más filtros <span class="crm-badge" hidden>0</span></button>');
  }
  function checks(name, items, sel) {
    if (!items.length) return '<div class="crm-sub" style="margin:0">Sin datos aún.</div>';
    return '<div class="crm-fil-lista">' + items.map(function (it) {
      return '<label><input type="checkbox" name="' + name + '" value="' + esc(it[0]) + '"' + ((sel || []).indexOf(it[0]) !== -1 ? ' checked' : '') + '/>' + esc(it[1]) + '</label>';
    }).join('') + '</div>';
  }
  function campo(lbl, html) { return '<div class="bk-field"><label class="bk-label">' + lbl + '</label>' + html + '</div>'; }
  function inp(name, type, ph) { return '<input class="bk-input" type="' + (type || 'text') + '" name="' + name + '" value="' + esc(F[name] || '') + '" placeholder="' + (ph || '') + '"/>'; }
  function sel(name, opts) { return '<select class="bk-select" name="' + name + '">' + opts.map(function (o) { return '<option value="' + o[0] + '"' + ((F[name] || '') === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') + '</select>'; }
  window.crmAbrirFiltros = async function () {
    await cargarExtrasFiltros();
    var tags = {}; cargar().forEach(function (c) { (c.etiquetas || []).forEach(function (t) { tags[t] = 1; }); });
    var fuentes = {}; cargar().forEach(function (c) { if (c.fuente) fuentes[norm(c.fuente)] = c.fuente; });
    (CAT.fuentes || []).forEach(function (f) { fuentes[norm(f.nombre)] = f.nombre; });
    var tiposOpc = (CAT.tipos && CAT.tipos.length ? CAT.tipos.map(function (t) { return [t.clave, t.nombre]; }) : Object.keys(ROLES).map(function (k) { return [k, ROLES[k].lbl]; }));
    var cuerpo =
      '<div class="crm-fil-grid">' +
        campo('Etapa', checks('etapas', (ETAPAS || []).map(function (e) { return [e.clave, e.nombre]; }), F.etapas)) +
        campo('Tipo', checks('tipos', tiposOpc, F.tipos)) +
        campo('Fuente', checks('fuentes', Object.keys(fuentes).sort().map(function (k) { return [k, fuentes[k]]; }), F.fuentes)) +
        campo('Etiquetas (cualquiera)', checks('tags', Object.keys(tags).sort().map(function (t) { return [t, t]; }), F.tags)) +
        campo('Probabilidad', checks('prob', (typeof PROBS !== 'undefined' ? PROBS : []).map(function (p) { return [p.v, p.l]; }), F.prob)) +
      '</div><div class="crm-fil-grid">' +
        campo('Creado desde', inp('creadoD', 'date')) + campo('Creado hasta', inp('creadoH', 'date')) +
        campo('Cambió de etapa desde', inp('etapaD', 'date')) + campo('Cambió de etapa hasta', inp('etapaH', 'date')) +
      '</div><div class="crm-fil-grid">' +
        campo('Tareas pendientes', sel('tareas', [['', 'Todas'], ['con', 'Con tareas pendientes'], ['sin', 'Sin tareas pendientes']])) +
        campo('Actividad', sel('actModo', [['sin', 'Sin actividad en'], ['con', 'Con actividad en']])) +
        campo('Días', inp('actN', 'number', 'Ej. 30')) +
        campo('Posibles duplicados', sel('dups', [['', 'Todos'], ['1', 'Sólo posibles duplicados']])) +
      '</div><div class="crm-sub" style="margin:var(--sp-3) 0 0">Le interesó (según su requerimiento)</div><div class="crm-fil-grid">' +
        campo('Operación', sel('intOp', [['', 'Cualquiera'], ['venta', 'Venta'], ['renta', 'Renta'], ['preventa', 'Preventa'], ['renta_temporal', 'Renta temporal']])) +
        campo('Tipo de inmueble', '<select class="bk-select" name="intTipo">' + (window.bkCat ? window.bkCat.tiposOptions(F.intTipo || '', { vacio: 'Cualquiera' }) : '<option value="">Cualquiera</option>') + '</select>') +
        campo('Zona (colonia o ciudad)', inp('intZona', 'text', 'Ej. Altozano')) +
        campo('Precio desde', inp('intPmin', 'number')) + campo('Precio hasta', inp('intPmax', 'number')) +
      '</div>';
    var ov = document.createElement('div');
    ov.className = 'bk-overlay bk-overlay--sheet crm-modal';
    ov.innerHTML = '<div class="bk-modal" role="dialog" aria-modal="true"><div class="bk-modal__head"><div class="bk-modal__title">Más filtros</div></div>' +
      '<form class="bk-modal__body" onsubmit="return false">' + cuerpo + '</form>' +
      '<div class="bk-modal__foot"><button class="bk-btn bk-btn--ghost" data-limpiar>Limpiar</button><button class="bk-btn bk-btn--forest" data-ok>Aplicar</button></div></div>';
    document.body.appendChild(ov);
    requestAnimationFrame(function () { ov.classList.add('is-open'); });
    var cerrar = function () { ov.classList.remove('is-open'); setTimeout(function () { ov.remove(); }, 250); };
    ov.addEventListener('click', function (e) { if (e.target === ov) cerrar(); });
    ov.querySelector('[data-limpiar]').onclick = function () { F = {}; cerrar(); pintarBoton(); rerender(); };
    ov.querySelector('[data-ok]').onclick = function () {
      var fd = new FormData(ov.querySelector('form')); var n = {};
      ['creadoD', 'creadoH', 'etapaD', 'etapaH', 'tareas', 'actModo', 'actN', 'dups', 'intOp', 'intTipo', 'intZona', 'intPmin', 'intPmax'].forEach(function (k) { var v = fd.get(k); if (v) n[k] = v; });
      ['etapas', 'tipos', 'fuentes', 'tags', 'prob'].forEach(function (k) { var v = fd.getAll(k); if (v.length) n[k] = v; });
      if (!n.actN) delete n.actModo;
      F = n; cerrar(); pintarBoton(); rerender();
    };
  };
  function rerender() { if (VISTA === 'pipeline' && typeof renderPipeline === 'function') renderPipeline(); else if (typeof renderActual === 'function') renderActual(); }

  // ════════════════════════════════════════════════════════════════════
  // 7. Acciones en lote (vista Lista)
  // ════════════════════════════════════════════════════════════════════
  function montarLote() {
    var bar = g('c-bulk-bar'); if (!bar || g('crm-lote-btn')) return;
    var del = bar.querySelector('.cbulk-bar__btn--danger');
    del.insertAdjacentHTML('beforebegin', '<button class="cbulk-bar__btn" id="crm-lote-btn" onclick="crmLoteMenu(event)">Acciones</button>');
  }
  window.crmLoteMenu = function (ev) {
    ev.stopPropagation();
    var viejo = g('crm-lote-pop'); if (viejo) { viejo.remove(); return; }
    var admin = typeof cEsAdminOrg !== 'undefined' && cEsAdminOrg && typeof cEsEmpresa !== 'undefined' && cEsEmpresa;
    var pop = document.createElement('div'); pop.id = 'crm-lote-pop'; pop.className = 'crm-lote-pop';
    pop.innerHTML = (admin ? '<button data-a="asignar">Asignar a…</button>' : '') +
      '<button data-a="etapa">Cambiar etapa…</button><button data-a="tag+">Agregar etiquetas…</button><button data-a="tag-">Quitar etiquetas…</button>' +
      '<button data-a="csv">Exportar CSV</button>';
    document.body.appendChild(pop);
    var r = ev.currentTarget.getBoundingClientRect();
    pop.style.left = Math.max(8, Math.min(window.innerWidth - 232, r.left)) + 'px';
    pop.style.bottom = (window.innerHeight - r.top + 8) + 'px';
    pop.onclick = function (e) { var b = e.target.closest('[data-a]'); if (!b) return; pop.remove(); loteAccion(b.dataset.a); };
    setTimeout(function () { document.addEventListener('click', function f() { if (g('crm-lote-pop')) g('crm-lote-pop').remove(); document.removeEventListener('click', f); }); }, 0);
  };
  function idsSel() { return typeof cSel !== 'undefined' ? Array.from(cSel) : []; }
  async function loteAccion(a) {
    var ids = idsSel(); if (!ids.length) return;
    if (a === 'csv') return exportarCsv(cargar().filter(function (c) { return ids.indexOf(String(c.id)) !== -1; }));
    var cuerpo, construir;
    if (a === 'asignar') {
      cuerpo = '<select class="bk-select" id="crm-l-v"><option value="">Sin asignar</option>' + (cMiembros || []).filter(function (m) { return m.activo !== false; })
        .map(function (m) { return '<option value="' + esc(m.user_id) + '">' + esc(m.nombre || m.email || 'Agente') + '</option>'; }).join('') + '</select>';
      construir = function (v) { return v ? { asignado_a: v } : { quitar_asignado: true }; };
    } else if (a === 'etapa') {
      cuerpo = '<select class="bk-select" id="crm-l-v">' + (ETAPAS || []).map(function (e) { return '<option value="' + esc(e.clave) + '">' + esc(e.nombre) + '</option>'; }).join('') + '</select>' +
        '<p class="crm-sub">Los que no estaban en el pipeline se marcan como potenciales.</p>';
      construir = function (v) { return { estatus: v }; };
    } else {
      cuerpo = '<input class="bk-input" id="crm-l-v" placeholder="vip, crédito"/>';
      construir = function (v) {
        var t = v.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
        return a === 'tag+' ? { etiquetas_agregar: t } : { etiquetas_quitar: t };
      };
    }
    var titulos = { asignar: 'Asignar', etapa: 'Cambiar etapa', 'tag+': 'Agregar etiquetas', 'tag-': 'Quitar etiquetas' };
    var ov = document.createElement('div');
    ov.className = 'bk-overlay bk-overlay--sheet crm-modal';
    ov.innerHTML = '<div class="bk-modal"><div class="bk-modal__head"><div class="bk-modal__title">' + titulos[a] + ' (' + ids.length + ')</div></div>' +
      '<div class="bk-modal__body">' + cuerpo + '</div><div class="bk-modal__foot"><button class="bk-btn bk-btn--ghost" data-x>Cancelar</button><button class="bk-btn bk-btn--forest" data-ok>Aplicar</button></div></div>';
    document.body.appendChild(ov);
    requestAnimationFrame(function () { ov.classList.add('is-open'); });
    var cerrar = function () { ov.classList.remove('is-open'); setTimeout(function () { ov.remove(); }, 250); };
    ov.querySelector('[data-x]').onclick = cerrar;
    ov.querySelector('[data-ok]').onclick = async function () {
      var body = Object.assign({ ids: ids }, construir(ov.querySelector('#crm-l-v').value));
      this.disabled = true;
      try {
        var r = await api('/crm/contactos/lote', { method: 'POST', json: body });
        cerrar(); toast((r.actualizados || 0) + ' actualizados' + (r.sin_permiso ? ' · ' + r.sin_permiso + ' sin permiso' : ''));
        await cargarRemoto(); renderActual();
      } catch (e) { this.disabled = false; toast(e.message); }
    };
  }
  function exportarCsv(lista) {
    var per = window.crmPermisos || {};
    if (per.exportar === false) { toast('No tienes permiso para descargar y exportar.'); return; }
    var cols = {};
    lista.forEach(function (c) { Object.keys(c).forEach(function (k) { cols[k] = 1; }); });
    var pref = ['id', 'nombre', 'telefono', 'wa', 'email', 'tipo', 'estatus', 'fuente', 'etiquetas', 'empresa', 'puesto'];
    var keys = pref.filter(function (k) { return cols[k]; }).concat(Object.keys(cols).filter(function (k) { return pref.indexOf(k) === -1; }).sort());
    var celda = function (v) {
      if (v == null) v = ''; else if (Array.isArray(v)) v = v.map(function (x) { return typeof x === 'object' ? (x.numero || x.correo || JSON.stringify(x)) : x; }).join('; ');
      else if (typeof v === 'object') v = JSON.stringify(v);
      v = String(v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
    };
    var csv = [keys.join(',')].concat(lista.map(function (c) { return keys.map(function (k) { return celda(c[k]); }).join(','); })).join('\r\n');
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
    a.download = 'contactos-' + new Date().toISOString().slice(0, 10) + '.csv';
    document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
    toast(lista.length + ' contactos exportados');
  }

  // ════════════════════════════════════════════════════════════════════
  // Arranque: se recalculan duplicados cada vez que la lista se repinta.
  // ════════════════════════════════════════════════════════════════════
  if (typeof renderActual === 'function') {
    var _renderOrig = renderActual;
    renderActual = function () { calcularDuplicados(); return _renderOrig.apply(this, arguments); };
  }
  async function init() {
    montarVistas(); montarFiltros(); montarLote(); montarFormulario();
    try {
      var org = await api('/org');
      window.crmPermisos = org.permisos || {};
    } catch (e) {}
    if (await cargarCatalogos()) rerender();
    listo = true;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
