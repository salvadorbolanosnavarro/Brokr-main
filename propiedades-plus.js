// ─────────────────────────────────────────────────────────────────────────
// propiedades-plus.js · Inventario completo en "Tus inmuebles"
//
//   · Editor de varias operaciones (venta, renta, preventa, renta temporal,
//     remate) con precio, moneda, unidad y periodo propios.
//   · Tipos agrupados del catálogo (inmuebles-catalogo.js).
//   · Características con casillas + "Otras características".
//   · Filtros avanzados, vista de mapa (Leaflet + OpenStreetMap) y acciones
//     en lote (asignar, etiquetas, estatus, archivar, exportar CSV/Excel).
//
// Depende de las variables y funciones globales de propiedades.html (g,
// allProps, filteredProps, selectedIds, sbFetch, getValidToken, API_BASE,
// mostrarToast, filterProps, renderPage, loadProps, pMiembros…) y de
// inmuebles-catalogo.js (window.bkCat).
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var C = window.bkCat;
  if (!C) return;
  var esc = C.esc;

  // Columnas que agregan las migraciones de paridad. Si la base todavía no
  // las tiene, el guardado reintenta sin ellas para no bloquear al usuario.
  var COLS_EXT = ['subtipo', 'operaciones', 'precio_unidad', 'mantenimiento_incluido', 'antiguedad',
    'condicion', 'disposicion', 'orientacion', 'pisos_edificio', 'caracteristicas',
    'otras_caracteristicas', 'lat', 'lng', 'fecha_cierre', 'videos', 'tours', 'documentos'];
  window.pxQuitarExtendidas = function (obj) {
    var out = {};
    Object.keys(obj).forEach(function (k) { if (COLS_EXT.indexOf(k) === -1) out[k] = obj[k]; });
    return out;
  };
  window.pxEsErrorColumna = function (err) {
    var m = String((err && err.message) || err || '');
    return m.indexOf('PGRST204') !== -1 || /Could not find the .* column/i.test(m);
  };

  // ── Normalización (idéntica a core/catalogo_inmuebles.normaliza) ──
  function normaliza(t) {
    return String(t || '').normalize('NFKD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  }
  var ALIAS = {};
  C.data.caracteristicas.forEach(function (gr) {
    gr.items.forEach(function (it) {
      [it.label, it.key.replace(/_/g, ' ')].concat(it.alias || []).forEach(function (n) {
        var k = normaliza(n); if (!(k in ALIAS)) ALIAS[k] = it.key;
      });
    });
  });
  function clasificar(textos) {
    var claves = [], otras = [];
    (textos || []).forEach(function (t) {
      if (!t || !String(t).trim()) return;
      var k = ALIAS[normaliza(t)];
      if (k) { if (claves.indexOf(k) === -1) claves.push(k); }
      else if (otras.indexOf(String(t).trim()) === -1) otras.push(String(t).trim());
    });
    return { claves: claves, otras: otras };
  }
  window.pxCaracteristicasDe = function (p) {
    if (p && Array.isArray(p.caracteristicas) && p.caracteristicas.length) return p.caracteristicas;
    return clasificar(p && p.amenidades).claves;
  };

  // ════════════════════════════════════════════════════════════════════
  // FORMULARIO
  // ════════════════════════════════════════════════════════════════════
  function opRowHtml(o, idx) {
    o = o || {};
    var tipo = o.tipo || 'venta';
    var precio = o.precio ? '$' + Number(o.precio).toLocaleString('es-MX') : '';
    return '<div class="px-op" data-idx="' + idx + '">' +
      '<div class="pf-field px-op__tipo"><label>Operación</label><select data-k="tipo" onchange="pxOpCambio()">' +
        C.listaOptions(C.data.operaciones, tipo) + '</select></div>' +
      '<div class="pf-field px-op__precio"><label>Precio</label><input type="text" inputmode="numeric" data-k="precio" placeholder="$2,500,000" value="' + esc(precio) + '" oninput="propFmtMoney(this);pxOpCambio()"' + (idx === 0 ? ' required' : '') + '/></div>' +
      '<div class="pf-field"><label>Moneda</label><select data-k="moneda" onchange="pxOpCambio()">' +
        C.listaOptions([{ key: 'MXN', label: 'MXN' }, { key: 'USD', label: 'USD' }], o.moneda || 'MXN') + '</select></div>' +
      '<div class="pf-field"><label>' + (tipo === 'renta_temporal' ? 'Periodo' : 'Unidad') + '</label>' +
        (tipo === 'renta_temporal'
          ? '<select data-k="periodo" onchange="pxOpCambio()">' + C.listaOptions(C.data.periodos, o.periodo || 'noche') + '</select>'
          : '<select data-k="unidad" onchange="pxOpCambio()">' + C.listaOptions(C.data.unidades, o.unidad || 'total') + '</select>') +
      '</div>' +
      '<button type="button" class="px-op__del" title="Quitar operación" aria-label="Quitar operación" onclick="pxOpQuitar(' + idx + ')"' + (idx === 0 ? ' disabled' : '') + '>' +
        '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M6 18L18 6M6 6l12 12"/></svg></button>' +
    '</div>';
  }
  function leerOps() {
    return Array.prototype.map.call(document.querySelectorAll('#px-ops .px-op'), function (row) {
      var o = {};
      row.querySelectorAll('[data-k]').forEach(function (el) { o[el.dataset.k] = el.value; });
      o.precio = typeof getRawNum === 'function' ? getRawNum(String(o.precio || '')) : Number(String(o.precio || '').replace(/[^0-9.]/g, ''));
      if (!o.precio) o.precio = null; else o.precio = Number(o.precio);
      if (o.tipo !== 'renta_temporal') delete o.periodo;
      if (!o.unidad) o.unidad = 'total';
      return o;
    });
  }
  function pintarOps(ops) {
    var cont = g('px-ops'); if (!cont) return;
    if (!ops || !ops.length) ops = [{ tipo: 'venta', moneda: 'MXN', unidad: 'total' }];
    cont.innerHTML = ops.map(opRowHtml).join('');
    sincronizarOps();
  }
  // Las columnas viejas (operacion/precio/moneda) se llenan con la primera.
  function sincronizarOps() {
    var ops = leerOps(), f = g('prop-form');
    if (!f || !ops.length) return;
    var o = ops[0];
    if (f.elements['operacion']) f.elements['operacion'].value = C.opLegacy(o.tipo) || '';
    if (f.elements['precio']) f.elements['precio'].value = o.precio != null ? String(o.precio) : '';
    if (f.elements['moneda']) f.elements['moneda'].value = o.moneda || 'MXN';
    if (f.elements['operaciones_json']) f.elements['operaciones_json'].value = JSON.stringify(ops);
    if (typeof pfActualizarComision === 'function') pfActualizarComision(C.opLegacy(o.tipo) || '');
  }
  window.pxOpCambio = function () {
    // Si cambió el tipo de alguna fila, se repinta para mostrar periodo/unidad.
    var ops = leerOps();
    var rows = document.querySelectorAll('#px-ops .px-op');
    var repintar = false;
    rows.forEach(function (row, i) {
      var tieneP = !!row.querySelector('[data-k="periodo"]');
      if ((ops[i].tipo === 'renta_temporal') !== tieneP) repintar = true;
    });
    if (repintar) pintarOps(ops); else sincronizarOps();
  };
  window.pxOpAgregar = function () {
    var ops = leerOps();
    var usadas = ops.map(function (o) { return o.tipo; });
    var sig = C.data.operaciones.filter(function (o) { return usadas.indexOf(o.key) === -1; })[0];
    ops.push({ tipo: sig ? sig.key : 'venta', moneda: 'MXN', unidad: 'total' });
    pintarOps(ops);
  };
  window.pxOpQuitar = function (idx) {
    var ops = leerOps(); if (idx <= 0 || idx >= ops.length) return;
    ops.splice(idx, 1); pintarOps(ops);
  };

  function pintarCaract(sel) {
    var cont = g('px-caract'); if (!cont) return;
    cont.innerHTML = C.caractCheckboxes('caracteristicas', sel || []);
  }

  // ── Multimedia: documentos públicos ──
  var docs = [];
  var MAX_DOC = 15 * 1024 * 1024;
  function pintarDocs() {
    var ul = g('px-docs-list'); if (!ul) return;
    ul.innerHTML = docs.map(function (d, i) {
      return '<li><a href="' + esc(d.url) + '" target="_blank" rel="noopener">' + esc(d.nombre) + '</a>' +
        '<button type="button" class="px-op__del" data-quitar-doc="' + i + '" aria-label="Quitar documento">' +
        '<svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M6 18L18 6M6 6l12 12"/></svg></button></li>';
    }).join('');
  }
  async function subirDocumentos(e) {
    var files = Array.from(e.target.files || []); if (!files.length) return;
    var prog = g('px-docs-progress');
    var token = await getValidToken();
    if (!token) { prog.textContent = 'Tu sesión expiró. Vuelve a iniciar sesión.'; return; }
    var carpeta = (typeof pOrgId !== 'undefined' && pOrgId) || (typeof getCurrentUserId === 'function' && getCurrentUserId()) || 'sin-cuenta';
    for (var i = 0; i < files.length; i++) {
      var f = files[i];
      if (f.size > MAX_DOC) { prog.textContent = f.name + ' pesa más de 15 MB; no se subió.'; continue; }
      if (!/^(application\/pdf|image\/)/.test(f.type)) { prog.textContent = f.name + ' no es PDF ni imagen; no se subió.'; continue; }
      prog.textContent = 'Subiendo ' + (i + 1) + ' de ' + files.length + '…';
      var limpio = f.name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Za-z0-9._-]+/g, '_').slice(-80);
      var ruta = carpeta + '/' + Date.now() + '_' + Math.random().toString(36).slice(2, 7) + '_' + limpio;
      try {
        var r = await fetch(SB_URL + '/storage/v1/object/documentos-publicos/' + ruta, {
          method: 'POST', body: f,
          headers: { apikey: SB_KEY, Authorization: 'Bearer ' + token, 'Content-Type': f.type || 'application/octet-stream', 'x-upsert': 'true' }
        });
        if (!r.ok) throw new Error((await r.text()).slice(0, 160));
        docs.push({ nombre: f.name, url: SB_URL + '/storage/v1/object/public/documentos-publicos/' + ruta, tipo: f.type, tamano: f.size });
        pintarDocs();
        if (typeof propFormDirty !== 'undefined') propFormDirty = true;
      } catch (err) { prog.textContent = 'No se pudo subir ' + f.name + ': ' + err.message; return; }
    }
    prog.textContent = '';
    e.target.value = '';
  }

  // ── Fotos: tope de 50 y aviso de baja resolución ──
  var MAX_FOTOS = 50, MIN_LADO = 500;
  function marcarBajaResolucion() {
    document.querySelectorAll('#fotos-preview .foto-preview-item img').forEach(function (img) {
      function revisar() {
        var item = img.closest('.foto-preview-item'); if (!item || !img.naturalWidth) return;
        var baja = img.naturalWidth < MIN_LADO || img.naturalHeight < MIN_LADO;
        item.classList.toggle('px-baja-res', baja);
        if (baja && !item.querySelector('.px-baja-res__tag')) {
          item.insertAdjacentHTML('beforeend', '<span class="px-baja-res__tag" title="' + img.naturalWidth + '×' + img.naturalHeight + ' px">Baja resolución</span>');
        }
      }
      if (img.complete) revisar(); else img.addEventListener('load', revisar, { once: true });
    });
    var nota = g('px-fotos-nota');
    if (nota && typeof uploadedFotoUrls !== 'undefined') {
      var n = uploadedFotoUrls.length;
      nota.textContent = n >= MAX_FOTOS
        ? 'Llegaste al máximo de ' + MAX_FOTOS + ' fotos.'
        : 'Hasta ' + MAX_FOTOS + ' fotos (' + (MAX_FOTOS - n) + ' disponibles). Recomendado: al menos ' + MIN_LADO + ' px por lado.';
    }
  }
  if (typeof renderFotosPreview === 'function') {
    var _renderFotosOrig = renderFotosPreview;
    renderFotosPreview = function () { _renderFotosOrig(); marcarBajaResolucion(); };
  }
  if (typeof initFotoUpload === 'function') {
    var _initFotoOrig = initFotoUpload;
    initFotoUpload = function () {
      _initFotoOrig();
      var input = g('fotos-upload'); if (!input || !input.onchange) return;
      var subirOrig = input.onchange;
      input.onchange = function (e) {
        var libres = MAX_FOTOS - uploadedFotoUrls.length;
        var files = Array.from(e.target.files || []);
        if (libres <= 0) { mostrarToast('Ya tienes ' + MAX_FOTOS + ' fotos, el máximo por inmueble.'); input.value = ''; return; }
        if (files.length > libres) {
          mostrarToast('Sólo se subirán ' + libres + ' de ' + files.length + ' fotos (máximo ' + MAX_FOTOS + ').');
          var dt = new DataTransfer(); files.slice(0, libres).forEach(function (f) { dt.items.add(f); });
          // e.target.files es de sólo lectura en el evento; se pasa un evento equivalente.
          return subirOrig.call(input, { target: { files: dt.files, value: '' } }).then(function () { input.value = ''; });
        }
        return subirOrig.call(input, e);
      };
    };
  }

  // Lo llama openPropForm() después de llenar el formulario.
  window.pxFormCargar = function (p) {
    var f = g('prop-form'); if (!f) return;
    if (f.elements['tipo']) f.elements['tipo'].innerHTML = C.tiposOptions(p ? C.tipoDe(p) : '', { vacio: 'Seleccionar' });
    if (p && f.elements['tipo']) {
      var t = C.tipoDe(p);
      if (t && f.elements['tipo'].value !== t) {
        var opt = document.createElement('option'); opt.value = t; opt.textContent = t;
        f.elements['tipo'].insertBefore(opt, f.elements['tipo'].firstChild); f.elements['tipo'].value = t;
      }
    }
    pintarOps(p ? C.operaciones(p) : null);
    var otras = p ? (p.otras_caracteristicas || '') : '';
    var sel = [];
    if (p) {
      if (Array.isArray(p.caracteristicas) && p.caracteristicas.length) sel = p.caracteristicas;
      else {
        var cl = clasificar(p.amenidades);
        sel = cl.claves;
        if (!otras && cl.otras.length) otras = cl.otras.join(', ');
      }
    }
    pintarCaract(sel);
    if (f.elements['otras_caracteristicas']) f.elements['otras_caracteristicas'].value = otras;
    if (g('px-videos')) g('px-videos').value = ((p && p.videos) || []).join('\n');
    if (g('px-tours')) g('px-tours').value = ((p && p.tours) || []).join('\n');
    docs = (p && Array.isArray(p.documentos)) ? p.documentos.slice() : [];
    pintarDocs();
    if (g('px-docs-progress')) g('px-docs-progress').textContent = '';
  };

  // Lo llama saveProp() con el objeto ya armado; ajusta los campos nuevos.
  window.pxFormAplicar = function (data, form) {
    sincronizarOps();
    var ops = leerOps().filter(function (o) { return o.tipo; });
    data.operaciones = ops;
    data.precio_unidad = (ops[0] && ops[0].unidad) || 'total';
    if (ops[0]) {
      data.operacion = C.opLegacy(ops[0].tipo);
      data.precio = ops[0].precio;
      data.moneda = ops[0].moneda || 'MXN';
    }
    delete data.operaciones_json;
    // Tipo: el select trae el subtipo; la columna vieja guarda la familia.
    if (data.tipo) { data.subtipo = data.tipo; data.tipo = C.tipoFamilia(data.tipo); }
    var claves = new FormData(form).getAll('caracteristicas');
    data.caracteristicas = claves;
    var otras = String(data.otras_caracteristicas || '').trim();
    data.otras_caracteristicas = otras || null;
    // amenidades (texto) se sigue llenando para lo que aún la lee (PDF, Broq).
    var am = claves.map(C.caractLabel).concat(otras ? otras.split(',').map(function (s) { return s.trim(); }).filter(Boolean) : []);
    data.amenidades = am.length ? am : null;
    if (g('px-videos')) data.videos = C.ligas(g('px-videos').value, true);
    if (g('px-tours')) data.tours = C.ligas(g('px-tours').value, false);
    data.documentos = docs.slice();
    if (Array.isArray(data.fotos) && data.fotos.length > MAX_FOTOS) data.fotos = data.fotos.slice(0, MAX_FOTOS);
    ['antiguedad', 'pisos_edificio'].forEach(function (k) { if (data[k] !== undefined && data[k] !== null && data[k] !== '') data[k] = parseInt(data[k], 10); });
    ['lat', 'lng'].forEach(function (k) { if (data[k] !== undefined && data[k] !== null && data[k] !== '') data[k] = parseFloat(data[k]); });
    return data;
  };

  // ════════════════════════════════════════════════════════════════════
  // FILTROS AVANZADOS
  // ════════════════════════════════════════════════════════════════════
  var F = {};   // estado de filtros avanzados
  function vacio(v) { return v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length); }
  function n(v) { var x = Number(v); return isFinite(x) ? x : 0; }
  function fecha(v) { return v ? new Date(v).getTime() : null; }
  function enRango(iso, desde, hasta) {
    if (!desde && !hasta) return true;
    if (!iso) return false;
    var t = fecha(iso);
    if (desde && t < fecha(desde + 'T00:00:00')) return false;
    if (hasta && t > fecha(hasta + 'T23:59:59')) return false;
    return true;
  }

  window.pxPasaFiltros = function (p) {
    if (!vacio(F.rec) && n(p.recamaras) < n(F.rec)) return false;
    if (!vacio(F.ban) && n(p.banos) < n(F.ban)) return false;
    if (!vacio(F.est) && n(p.estacionamientos) < n(F.est)) return false;
    if (!vacio(F.m2cMin) && n(p.m2_construccion) < n(F.m2cMin)) return false;
    if (!vacio(F.m2cMax) && (!p.m2_construccion || n(p.m2_construccion) > n(F.m2cMax))) return false;
    if (!vacio(F.m2tMin) && n(p.m2_terreno) < n(F.m2tMin)) return false;
    if (!vacio(F.m2tMax) && (!p.m2_terreno || n(p.m2_terreno) > n(F.m2tMax))) return false;
    if (!vacio(F.car)) {
      var tiene = window.pxCaracteristicasDe(p);
      for (var i = 0; i < F.car.length; i++) if (tiene.indexOf(F.car[i]) === -1) return false;
    }
    if (!vacio(F.tags)) {
      var et = Array.isArray(p.etiquetas) ? p.etiquetas : [];
      if (!F.tags.some(function (t) { return et.indexOf(t) !== -1; })) return false;
    }
    if (F.fotos === 'con' && !(p.fotos && p.fotos.length)) return false;
    if (F.fotos === 'sin' && p.fotos && p.fotos.length) return false;
    if (F.exclusiva === 'si' && p.exclusiva !== 'si') return false;
    if (F.exclusiva === 'no' && p.exclusiva === 'si') return false;
    if (F.comparte === 'si' && p.comision_compartida !== true && p.en_bolsa !== true) return false;
    if (F.comparte === 'no' && (p.comision_compartida === true || p.en_bolsa === true)) return false;
    if (!enRango(p.created_at, F.creadaDesde, F.creadaHasta)) return false;
    if (!enRango(p.updated_at, F.actDesde, F.actHasta)) return false;
    if (!enRango(p.fecha_cierre, F.cierreDesde, F.cierreHasta)) return false;
    if (!vacio(F.ciudades) && F.ciudades.indexOf(normaliza(p.ciudad)) === -1) return false;
    if (!vacio(F.colonias) && F.colonias.indexOf(normaliza(p.colonia)) === -1) return false;
    return true;
  };
  function contarActivos() {
    return Object.keys(F).filter(function (k) { return !vacio(F[k]); }).length;
  }
  function pintarBadge() {
    var b = g('px-fil-badge'), btn = g('px-fil-btn'); if (!b || !btn) return;
    var c = contarActivos();
    b.textContent = c; b.style.display = c ? '' : 'none';
    btn.classList.toggle('is-active', c > 0);
  }
  function valoresUnicos(campo) {
    var m = {};
    (allProps || []).forEach(function (p) {
      var v = (p[campo] || '').trim(); if (!v) return;
      var k = normaliza(v); if (!m[k]) m[k] = { k: k, label: v, c: 0 }; m[k].c++;
    });
    return Object.keys(m).map(function (k) { return m[k]; }).sort(function (a, b) { return a.label.localeCompare(b.label, 'es'); });
  }
  function listaChecks(name, items, sel, buscar) {
    if (!items.length) return '<div class="px-fil-vacio">Sin datos aún.</div>';
    return (buscar ? '<div class="pf-field px-fil-buscar"><input type="text" placeholder="Buscar…" oninput="pxFiltrarLista(this)"/></div>' : '') +
      '<div class="px-fil-lista">' + items.map(function (it) {
        return '<label class="bk-car-item" data-txt="' + esc(normaliza(it.label)) + '"><input type="checkbox" name="' + name + '" value="' + esc(it.k) + '"' +
          (sel && sel.indexOf(it.k) !== -1 ? ' checked' : '') + '/><span>' + esc(it.label) + (it.c ? ' <span style="color:var(--mute)">(' + it.c + ')</span>' : '') + '</span></label>';
      }).join('') + '</div>';
  }
  window.pxFiltrarLista = function (inp) {
    var q = normaliza(inp.value);
    var lista = inp.closest('.pf-field').nextElementSibling;
    lista.querySelectorAll('.bk-car-item').forEach(function (l) { l.style.display = !q || l.dataset.txt.indexOf(q) !== -1 ? '' : 'none'; });
  };
  function campo(label, html) { return '<div class="pf-field"><label>' + label + '</label>' + html + '</div>'; }
  function inNum(k, ph) { return '<input type="number" inputmode="numeric" min="0" name="' + k + '" value="' + esc(F[k] || '') + '" placeholder="' + (ph || '') + '"/>'; }
  function inFecha(k) { return '<input type="date" name="' + k + '" value="' + esc(F[k] || '') + '"/>'; }
  function selSN(k, opts) {
    return '<select name="' + k + '">' + opts.map(function (o) { return '<option value="' + o[0] + '"' + ((F[k] || '') === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') + '</select>';
  }

  window.pxAbrirFiltros = function () {
    var tags = {};
    (allProps || []).forEach(function (p) { (p.etiquetas || []).forEach(function (t) { tags[t] = (tags[t] || 0) + 1; }); });
    var tagItems = Object.keys(tags).sort().map(function (t) { return { k: t, label: t, c: tags[t] }; });
    var html =
      '<div class="pf-section">Tamaño</div><div class="px-fil-grid">' +
        campo('Recámaras (mín.)', inNum('rec', '2')) + campo('Baños (mín.)', inNum('ban', '1')) + campo('Estacionamientos (mín.)', inNum('est', '1')) +
      '</div><div class="px-fil-grid">' +
        campo('m² construcción mín.', inNum('m2cMin')) + campo('m² construcción máx.', inNum('m2cMax')) +
        campo('m² terreno mín.', inNum('m2tMin')) + campo('m² terreno máx.', inNum('m2tMax')) +
      '</div>' +
      '<div class="pf-section">Ubicación</div><div class="px-fil-grid">' +
        campo('Ciudades', listaChecks('ciudades', valoresUnicos('ciudad'), F.ciudades, true)) +
        campo('Colonias', listaChecks('colonias', valoresUnicos('colonia'), F.colonias, true)) +
      '</div>' +
      '<div class="pf-section">Comercial</div><div class="px-fil-grid">' +
        campo('Fotos', selSN('fotos', [['', 'Todas'], ['con', 'Con fotos'], ['sin', 'Sin fotos']])) +
        campo('Exclusiva', selSN('exclusiva', [['', 'Todas'], ['si', 'Sí'], ['no', 'No']])) +
        campo('Comparte comisión', selSN('comparte', [['', 'Todas'], ['si', 'Sí'], ['no', 'No']])) +
      '</div>' +
      (tagItems.length ? '<div class="px-fil-grid">' + campo('Etiquetas (cualquiera)', listaChecks('tags', tagItems, F.tags, tagItems.length > 8)) + '</div>' : '') +
      '<div class="pf-section">Fechas</div><div class="px-fil-grid">' +
        campo('Creada desde', inFecha('creadaDesde')) + campo('Creada hasta', inFecha('creadaHasta')) +
        campo('Actualizada desde', inFecha('actDesde')) + campo('Actualizada hasta', inFecha('actHasta')) +
        campo('Cerrada desde', inFecha('cierreDesde')) + campo('Cerrada hasta', inFecha('cierreHasta')) +
      '</div>' +
      '<div class="pf-section">Características y financiamiento (todas las marcadas)</div>' +
      '<div class="px-car-wrap">' + C.caractCheckboxes('car', F.car || []) + '</div>';
    abrirModal('px-fil-modal', 'Más filtros', html,
      '<button type="button" class="pf-cancel-btn" onclick="pxLimpiarFiltros()">Limpiar</button>' +
      '<button type="button" class="pf-save-btn" onclick="pxAplicarFiltros()">Aplicar filtros</button>');
  };
  window.pxAplicarFiltros = function () {
    var form = g('px-fil-modal-form'); var fd = new FormData(form);
    var nuevo = {};
    ['rec', 'ban', 'est', 'm2cMin', 'm2cMax', 'm2tMin', 'm2tMax', 'fotos', 'exclusiva', 'comparte',
      'creadaDesde', 'creadaHasta', 'actDesde', 'actHasta', 'cierreDesde', 'cierreHasta'].forEach(function (k) {
      var v = fd.get(k); if (v) nuevo[k] = v;
    });
    ['ciudades', 'colonias', 'tags', 'car'].forEach(function (k) { var v = fd.getAll(k); if (v.length) nuevo[k] = v; });
    F = nuevo;
    cerrarModal('px-fil-modal'); pintarBadge(); filterProps();
  };
  window.pxLimpiarFiltros = function () { F = {}; cerrarModal('px-fil-modal'); pintarBadge(); filterProps(); };

  // ── Modal genérico (mismo look que el formulario de inmuebles) ──
  function abrirModal(id, titulo, cuerpo, acciones) {
    var ov = g(id);
    if (!ov) {
      ov = document.createElement('div'); ov.id = id; ov.className = 'prop-modal-overlay';
      ov.addEventListener('click', function (e) { if (e.target === ov) cerrarModal(id); });
      document.body.appendChild(ov);
    }
    ov.innerHTML = '<div class="prop-modal-box" onclick="event.stopPropagation()">' +
      '<div class="prop-modal-hdr"><h3>' + esc(titulo) + '</h3><button class="prop-modal-close" aria-label="Cerrar" onclick="pxCerrarModal(\'' + id + '\')">' +
      '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 18L18 6M6 6l12 12"/></svg></button></div>' +
      '<div class="prop-modal-body"><form id="' + id + '-form" onsubmit="return false">' + cuerpo +
      '<div class="pf-actions">' + acciones + '</div></form></div></div>';
    ov.style.display = 'flex';
  }
  function cerrarModal(id) { var ov = g(id); if (ov) ov.style.display = 'none'; }
  window.pxCerrarModal = cerrarModal;
  window.pxAbrirModal = abrirModal;

  // ════════════════════════════════════════════════════════════════════
  // MAPA (Leaflet + OpenStreetMap, sin llave)
  // ════════════════════════════════════════════════════════════════════
  var mapa = null, capa = null, mapaAbierto = false;
  function cargarLeaflet() {
    if (window.L) return Promise.resolve();
    return new Promise(function (res, rej) {
      var css = document.createElement('link'); css.rel = 'stylesheet';
      css.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css'; document.head.appendChild(css);
      var s = document.createElement('script'); s.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
      s.onload = res; s.onerror = function () { rej(new Error('No se pudo cargar el mapa')); }; document.head.appendChild(s);
    });
  }
  window.pxToggleMapa = function () {
    mapaAbierto = !mapaAbierto;
    g('px-map').classList.toggle('is-open', mapaAbierto);
    g('px-map-btn').classList.toggle('is-active', mapaAbierto);
    if (!mapaAbierto) { g('px-map-aviso').classList.remove('is-open'); return; }
    cargarLeaflet().then(function () {
      if (!mapa) {
        mapa = L.map('px-map', { scrollWheelZoom: false }).setView([19.70, -101.19], 12);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19, attribution: '&copy; OpenStreetMap'
        }).addTo(mapa);
      }
      setTimeout(function () { mapa.invalidateSize(); window.pxPintarMapa(); }, 50);
    }).catch(function (e) { mostrarToast(e.message); });
  };
  window.pxPintarMapa = function () {
    if (!mapaAbierto || !mapa || !window.L) return;
    if (capa) capa.remove();
    capa = L.featureGroup();
    var con = 0, sin = 0;
    (filteredProps || []).forEach(function (p) {
      var lat = Number(p.lat), lng = Number(p.lng);
      if (!p.lat || !p.lng || !isFinite(lat) || !isFinite(lng)) { sin++; return; }
      con++;
      var op = C.operaciones(p)[0];
      var html = '<div class="px-pop">' + (p.fotos && p.fotos[0] ? '<img src="' + esc(p.fotos[0]) + '" alt=""/>' : '') +
        '<strong>' + esc(p.titulo || '') + '</strong><span>' + esc([p.colonia, p.ciudad].filter(Boolean).join(', ')) + '</span>' +
        '<span>' + esc(op ? C.opLabel(op.tipo) + ' · ' + C.precioTexto(op) : '') + '</span>' +
        '<a href="propiedades.html?id=' + encodeURIComponent(p.id) + '" target="brokr_prop_' + esc(p.id) + '">Abrir ficha →</a></div>';
      L.marker([lat, lng]).bindPopup(html).addTo(capa);
    });
    capa.addTo(mapa);
    if (con) mapa.fitBounds(capa.getBounds().pad(0.15), { maxZoom: 15 });
    var av = g('px-map-aviso');
    av.textContent = con + ' en el mapa' + (sin ? ' · ' + sin + ' sin coordenadas (agrégalas en Editar → Ubicación, o vuelve a importar de EasyBroker)' : '');
    av.classList.add('is-open');
  };

  // ════════════════════════════════════════════════════════════════════
  // ACCIONES EN LOTE
  // ════════════════════════════════════════════════════════════════════
  function seleccion() { return (allProps || []).filter(function (p) { return selectedIds.has(p.id); }); }
  function puedeExportar() {
    var per = window.pPermisos || {};
    return per.exportar !== false;
  }
  window.pxBulkMenu = function (ev) {
    if (ev) ev.stopPropagation();
    var pop = g('px-bulk-pop');
    var abrir = !pop.classList.contains('is-open');
    if (abrir) {
      var esAdmin = typeof pEsAdminOrg !== 'undefined' && pEsAdminOrg;
      var empresa = typeof pEsEmpresa !== 'undefined' && pEsEmpresa;
      pop.innerHTML =
        (empresa && esAdmin ? '<button onclick="pxBulkAsignar()">Asignar agente…</button>' : '') +
        '<button onclick="pxBulkEtiquetas(true)">Agregar etiquetas…</button>' +
        '<button onclick="pxBulkEtiquetas(false)">Quitar etiquetas…</button>' +
        '<button onclick="pxBulkEstatus()">Cambiar estatus…</button>' +
        '<button onclick="pxBulkArchivar(true)">Archivar</button>' +
        '<button onclick="pxBulkArchivar(false)">Desarchivar</button>' +
        (puedeExportar() ? '<hr/><button onclick="pxExportar(\'csv\')">Exportar CSV</button><button onclick="pxExportar(\'xlsx\')">Exportar Excel</button>' : '');
    }
    pop.classList.toggle('is-open', abrir);
  };
  document.addEventListener('click', function (e) {
    var pop = g('px-bulk-pop');
    if (pop && pop.classList.contains('is-open') && !e.target.closest('.px-bulk-menu')) pop.classList.remove('is-open');
  });
  function cerrarPop() { var pop = g('px-bulk-pop'); if (pop) pop.classList.remove('is-open'); }

  // Lote vía backend: misma regla de permisos que editar un inmueble (dueño
  // o compañero activo de la organización), no la RLS del dueño.
  async function lote(body) {
    var token = await getValidToken();
    if (!token) throw new Error('Tu sesión expiró. Vuelve a iniciar sesión.');
    var r = await fetch(API_BASE + '/propiedades/lote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
      body: JSON.stringify(body)
    });
    var d = await r.json().catch(function () { return {}; });
    if (!r.ok) throw new Error(d.detail || 'Error');
    return d;
  }
  function reportar(d, total, que) {
    var msg = (d.actualizadas || 0) + ' de ' + total + ' ' + que;
    if (d.sin_permiso) msg += ' · ' + d.sin_permiso + ' sin permiso';
    mostrarToast(msg);
  }

  window.pxBulkEstatus = function () {
    cerrarPop();
    var opciones = [['activa', 'Activa'], ['reservada', 'Reservada'], ['en_proceso', 'En proceso'], ['vendida', 'Vendida'],
      ['rentada', 'Rentada'], ['suspendida', 'Suspendida'], ['no_activa', 'No activo (por revisar)']];
    abrirModal('px-bulk-modal', 'Cambiar estatus (' + selectedIds.size + ')',
      '<div class="pf-row"><div class="pf-field full"><label>Nuevo estatus</label><select name="estatus">' +
      opciones.map(function (o) { return '<option value="' + o[0] + '">' + o[1] + '</option>'; }).join('') + '</select></div></div>',
      '<button type="button" class="pf-cancel-btn" onclick="pxCerrarModal(\'px-bulk-modal\')">Cancelar</button>' +
      '<button type="button" class="pf-save-btn" onclick="pxBulkEstatusOk()">Aplicar</button>');
  };
  window.pxBulkEstatusOk = async function () {
    var est = g('px-bulk-modal-form').elements['estatus'].value;
    var ids = Array.from(selectedIds);
    try {
      var d = await lote({ ids: ids, set: { estatus: est } });
      cerrarModal('px-bulk-modal'); reportar(d, ids.length, 'con estatus actualizado'); await loadProps();
    } catch (e) { alert('No se pudo cambiar el estatus: ' + e.message); }
  };

  window.pxBulkArchivar = async function (archivar) {
    cerrarPop();
    var ids = Array.from(selectedIds);
    if (!confirm((archivar ? '¿Archivar ' : '¿Desarchivar ') + ids.length + ' inmuebles?')) return;
    try {
      var d = await lote({ ids: ids, set: { archivada: !!archivar } });
      reportar(d, ids.length, archivar ? 'archivados' : 'desarchivados');
      selectedIds.clear(); await loadProps();
    } catch (e) { alert('No se pudo archivar: ' + e.message); }
  };

  window.pxBulkEtiquetas = function (agregar) {
    cerrarPop();
    abrirModal('px-bulk-modal', (agregar ? 'Agregar' : 'Quitar') + ' etiquetas (' + selectedIds.size + ')',
      '<div class="pf-row"><div class="pf-field full"><label>Etiquetas <span style="color:var(--mute);font-weight:400">— separadas por coma</span></label>' +
      '<input type="text" name="tags" placeholder="destacada, urgente" autofocus/></div></div>',
      '<button type="button" class="pf-cancel-btn" onclick="pxCerrarModal(\'px-bulk-modal\')">Cancelar</button>' +
      '<button type="button" class="pf-save-btn" onclick="pxBulkEtiquetasOk(' + (agregar ? 'true' : 'false') + ')">Aplicar</button>');
  };
  window.pxBulkEtiquetasOk = async function (agregar) {
    var tags = g('px-bulk-modal-form').elements['tags'].value.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    if (!tags.length) return;
    var ids = Array.from(selectedIds);
    try {
      var d = await lote(agregar ? { ids: ids, etiquetas_agregar: tags } : { ids: ids, etiquetas_quitar: tags });
      cerrarModal('px-bulk-modal'); reportar(d, ids.length, 'actualizados'); await loadProps();
    } catch (e) { alert('No se pudieron actualizar las etiquetas: ' + e.message); }
  };

  window.pxBulkAsignar = function () {
    cerrarPop();
    var miembros = (typeof pMiembros !== 'undefined' && pMiembros) || [];
    abrirModal('px-bulk-modal', 'Asignar agente (' + selectedIds.size + ')',
      '<div class="pf-row"><div class="pf-field full"><label>Agente</label><select name="agente"><option value="">Sin asignar</option>' +
      miembros.map(function (m) { return '<option value="' + esc(m.user_id) + '">' + esc(m.nombre || m.email || 'Agente') + '</option>'; }).join('') +
      '</select></div></div>',
      '<button type="button" class="pf-cancel-btn" onclick="pxCerrarModal(\'px-bulk-modal\')">Cancelar</button>' +
      '<button type="button" class="pf-save-btn" onclick="pxBulkAsignarOk()">Asignar</button>');
  };
  window.pxBulkAsignarOk = async function () {
    var agente = g('px-bulk-modal-form').elements['agente'].value || null;
    var ids = Array.from(selectedIds).map(String);
    try {
      var token = await getValidToken();
      var r = await fetch(API_BASE + '/org/asignar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
        body: JSON.stringify({ tabla: 'propiedades', ids: ids, agente_user_id: agente })
      });
      if (!r.ok) throw new Error((await r.json().catch(function () { return {}; })).detail || 'Error');
      cerrarModal('px-bulk-modal'); mostrarToast(agente ? ids.length + ' asignados' : 'Asignación quitada a ' + ids.length); await loadProps();
    } catch (e) { alert('No se pudo asignar: ' + e.message); }
  };

  // ── Exportar (todas las columnas) ──
  function aplanar(p) {
    var o = {};
    Object.keys(p).forEach(function (k) {
      var v = p[k];
      if (k === 'operaciones') {
        v = C.operaciones(p).map(function (op) { return C.opLabel(op.tipo) + ': ' + C.precioTexto(op); }).join(' | ');
      } else if (k === 'caracteristicas') {
        v = (v || []).map(C.caractLabel).join('; ');
      } else if (k === 'subtipo' || (k === 'tipo' && !p.subtipo)) {
        v = C.tipoLabel(v);
      } else if (k === 'asignado_a' && v && typeof pNombreAgente === 'function') {
        v = pNombreAgente(v);
      } else if (Array.isArray(v)) {
        v = v.map(function (x) { return typeof x === 'object' ? JSON.stringify(x) : x; }).join('; ');
      } else if (v && typeof v === 'object') {
        v = JSON.stringify(v);
      }
      o[k] = v == null ? '' : v;
    });
    return o;
  }
  function columnas(filas) {
    var preferidas = ['id', 'clave_interna', 'titulo', 'subtipo', 'tipo', 'operaciones', 'operacion', 'precio', 'moneda', 'estatus',
      'calle', 'num_exterior', 'num_interior', 'colonia', 'ciudad', 'estado', 'cp', 'lat', 'lng',
      'm2_construccion', 'm2_terreno', 'recamaras', 'banos', 'medio_bano', 'estacionamientos'];
    var set = {};
    filas.forEach(function (f) { Object.keys(f).forEach(function (k) { set[k] = true; }); });
    var resto = Object.keys(set).filter(function (k) { return preferidas.indexOf(k) === -1; }).sort();
    return preferidas.filter(function (k) { return set[k]; }).concat(resto);
  }
  function descargar(blob, nombre) {
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = nombre;
    document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  window.pxExportar = async function (formato, lista) {
    cerrarPop();
    if (!puedeExportar()) { mostrarToast('No tienes permiso para descargar y exportar.'); return; }
    var props = lista || seleccion();
    if (!props.length) props = filteredProps || [];
    if (!props.length) { mostrarToast('No hay inmuebles para exportar.'); return; }
    var filas = props.map(aplanar), cols = columnas(filas);
    var nombre = 'inmuebles-' + new Date().toISOString().slice(0, 10);
    if (formato === 'xlsx') {
      try {
        if (!window.XLSX) await new Promise(function (res, rej) {
          var s = document.createElement('script'); s.src = 'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js';
          s.onload = res; s.onerror = rej; document.head.appendChild(s);
        });
        var ws = XLSX.utils.json_to_sheet(filas, { header: cols });
        var wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws, 'Inmuebles');
        XLSX.writeFile(wb, nombre + '.xlsx');
        mostrarToast(props.length + ' inmuebles exportados');
        return;
      } catch (e) { mostrarToast('No se pudo generar Excel; se descarga CSV.'); }
    }
    var csv = [cols.join(',')].concat(filas.map(function (f) {
      return cols.map(function (c) {
        var v = String(f[c] == null ? '' : f[c]);
        return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
      }).join(',');
    })).join('\r\n');
    descargar(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }), nombre + '.csv');
    mostrarToast(props.length + ' inmuebles exportados');
  };

  // ════════════════════════════════════════════════════════════════════
  // CLIENTES POTENCIALES (ficha del inmueble → contactos cuyo requerimiento
  // coincide; routers/alertas.py)
  // ════════════════════════════════════════════════════════════════════
  function bloquePotenciales(p) {
    var pane = g('f-pane-detalles'); if (!pane || g('px-potenciales')) return;
    pane.insertAdjacentHTML('beforeend', '<div class="bk-bloque" id="px-potenciales"><div class="bk-acciones">' +
      '<h3 class="bk-acciones__t">Clientes potenciales</h3><button class="bk-btn bk-btn--sm" id="px-pot-btn">Buscar clientes potenciales</button></div>' +
      '<div id="px-pot-lista"></div></div>');
    g('px-pot-btn').onclick = function () { buscarPotenciales(p.id); };
  }
  async function buscarPotenciales(pid) {
    var cont = g('px-pot-lista'); cont.innerHTML = '<div class="bk-cargando"></div>';
    try {
      var d = await window.bkApi('/alertas/clientes-potenciales/' + encodeURIComponent(pid));
      var lista = d.clientes || [];
      cont.innerHTML = lista.length ? lista.map(function (c) {
        return '<div class="bk-fila"><a class="bk-fila__cuerpo" href="contactos.html?id=' + encodeURIComponent(c.contacto_id) + '&tab=requerimiento" target="_blank">' +
          '<span class="bk-fila__t">' + esc(c.nombre || 'Contacto') + '</span><span class="bk-fila__d">' + esc((c.motivos || []).join(' · ')) + '</span></a>' +
          (c.ligado ? '<span class="pd-tag">Interesado</span>' : '<button class="bk-btn bk-btn--ghost bk-btn--sm" data-ligar="' + esc(c.contacto_id) + '">Ligar como interesado</button>') + '</div>';
      }).join('') : '<div class="bk-vacio"><p>Ningún requerimiento activo coincide con este inmueble todavía.</p></div>';
      cont.onclick = async function (e) {
        var b = e.target.closest('[data-ligar]'); if (!b) return;
        b.disabled = true;
        try {
          await window.bkApi('/alertas/ligar-interesado', { method: 'POST', json: { contacto_id: b.dataset.ligar, propiedad_id: pid } });
          b.outerHTML = '<span class="pd-tag">Interesado</span>'; mostrarToast('Ligado como interesado');
        } catch (err) { b.disabled = false; mostrarToast(err.message); }
      };
    } catch (e) { cont.innerHTML = '<div class="bk-vacio"><p>' + esc(e.message) + '</p></div>'; }
  }
  if (typeof pfRenderDetalles === 'function') {
    var _pfRenderOrig = pfRenderDetalles;
    pfRenderDetalles = function (p) { var r = _pfRenderOrig.apply(this, arguments); bloquePotenciales(p); return r; };
  }

  // ════════════════════════════════════════════════════════════════════
  // ARRANQUE
  // ════════════════════════════════════════════════════════════════════
  window.pxAmenidadesTexto = function (p) {
    return window.pxCaracteristicasDe(p).map(C.caractLabel)
      .concat(p.otras_caracteristicas ? String(p.otras_caracteristicas).split(',').map(function (x) { return x.trim(); }).filter(Boolean) : [])
      .join(', ');
  };

  // HTML que se inserta en propiedades.html (vive aquí para no crecer esa página).
  var SVG_MAS = '<svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" d="M12 5v14M5 12h14"/></svg>';
  var HTML_OPS =
    '<div class="pf-section">Operaciones y precios</div>' +
    '<div id="px-ops" class="px-ops"></div>' +
    '<button type="button" class="px-add" onclick="pxOpAgregar()">' + SVG_MAS + ' Agregar otra operación</button>' +
    '<input type="hidden" name="operacion"/><input type="hidden" name="precio"/>' +
    '<input type="hidden" name="moneda"/><input type="hidden" name="operaciones_json"/>';
  function fld(label, ctrl) { return '<div class="pf-field"><label>' + label + '</label>' + ctrl + '</div>'; }
  var NOTA = function (t) { return ' <span style="color:var(--mute);font-weight:400">— ' + t + '</span>'; };
  var HTML_EXTRA =
    '<div class="pf-row">' +
      fld('Mantenimiento incluido', '<select name="mantenimiento_incluido"><option value="no_indicado">No indicado</option><option value="si">Sí</option><option value="no">No</option></select>') +
      fld('Antigüedad (años)', '<input type="number" name="antiguedad" placeholder="5" min="0" max="300"/>') +
      fld('Pisos del edificio', '<input type="number" name="pisos_edificio" placeholder="8" min="0" max="200"/>') +
    '</div><div class="pf-row">' +
      fld('Condición', '<select name="condicion"></select>') +
      fld('Disposición', '<select name="disposicion"></select>') +
      fld('Orientación', '<select name="orientacion"></select>') +
    '</div><div class="pf-row">' +
      fld('Latitud' + NOTA('para el mapa'), '<input type="text" inputmode="decimal" name="lat" placeholder="19.7008"/>') +
      fld('Longitud', '<input type="text" inputmode="decimal" name="lng" placeholder="-101.1844"/>') +
    '</div>' +
    '<div class="pf-section">Características y financiamiento</div>' +
    '<div class="pf-row"><div class="pf-field full"><div id="px-caract" class="px-car-wrap"></div></div></div>' +
    '<div class="pf-row"><div class="pf-field full"><label>Otras características' + NOTA('lo que no está en la lista, separado por coma') + '</label>' +
      '<input type="text" name="otras_caracteristicas" placeholder="Vista a la presa, cuarto de juegos"/></div></div>';
  var HTML_TOOLS =
    '<button type="button" class="px-tool-btn" id="px-fil-btn" onclick="pxAbrirFiltros()">' +
      '<svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" d="M3 5h18M6 12h12M10 19h4"/></svg>' +
      ' Más filtros <span class="px-badge" id="px-fil-badge" style="display:none">0</span></button>' +
    '<button type="button" class="px-tool-btn" id="px-map-btn" onclick="pxToggleMapa()">' +
      '<svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"/></svg>' +
      ' Mapa</button>';

  var HTML_MULTI =
    '<div class="pf-section">Multimedia</div>' +
    '<div class="pf-row"><div class="pf-field full"><label>Videos de YouTube' + NOTA('una liga por renglón') + '</label>' +
      '<textarea id="px-videos" rows="2" placeholder="https://youtu.be/…"></textarea></div></div>' +
    '<div class="pf-row"><div class="pf-field full"><label>Tour virtual' + NOTA('Matterport, Kuula u otra liga https, una por renglón') + '</label>' +
      '<textarea id="px-tours" rows="2" placeholder="https://my.matterport.com/show/?m=…"></textarea></div></div>' +
    '<div class="pf-row"><div class="pf-field full"><label>Documentos públicos' + NOTA('planos, volantes, lista de precios · PDF o imagen, máx. 15 MB') + '</label>' +
      '<input type="file" id="px-docs-input" accept="application/pdf,image/*" multiple class="px-file"/>' +
      '<ul id="px-docs-list" class="px-docs"></ul><div id="px-docs-progress" class="px-nota"></div></div></div>';

  function montarHtml() {
    var w = g('px-ops-wrap'); if (w && !g('px-ops')) w.innerHTML = HTML_OPS;
    var e = g('px-campos-extra'); if (e && !g('px-caract')) e.innerHTML = HTML_EXTRA;
    var arch = g('props-arch-toggle');
    if (arch && !g('px-fil-btn')) arch.insertAdjacentHTML('beforebegin', HTML_TOOLS);
    var grid = g('props-grid');
    if (grid && !g('px-map')) grid.insertAdjacentHTML('beforebegin', '<div id="px-map-aviso" class="px-map-aviso"></div><div id="px-map" class="px-map"></div>');
    var fotosRow = g('fotos-upload') && g('fotos-upload').closest('.pf-row');
    if (fotosRow && !g('px-videos')) {
      fotosRow.insertAdjacentHTML('afterend', HTML_MULTI);
      var nota = document.createElement('div'); nota.className = 'px-nota'; nota.id = 'px-fotos-nota';
      nota.textContent = 'Hasta ' + MAX_FOTOS + ' fotos. Recomendado: al menos ' + MIN_LADO + ' px por lado.';
      g('fotos-upload').insertAdjacentElement('afterend', nota);
      g('px-docs-input').addEventListener('change', subirDocumentos);
      g('px-docs-list').addEventListener('click', function (e) {
        var b = e.target.closest('[data-quitar-doc]'); if (!b) return;
        docs.splice(Number(b.dataset.quitarDoc), 1); pintarDocs();
      });
    }
    var del = document.querySelector('#bulk-bar .bulk-bar__btn--danger');
    if (del && !g('px-bulk-pop')) del.insertAdjacentHTML('beforebegin',
      '<div class="px-bulk-menu"><button class="bulk-bar__btn" onclick="pxBulkMenu(event)">Acciones <svg width="10" height="6" viewBox="0 0 10 6" fill="none"><path stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" d="M1 1l4 4 4-4"/></svg></button><div class="px-bulk-pop" id="px-bulk-pop"></div></div>');
  }

  function init() {
    montarHtml();
    // Modal de cierre (Fase 6): archivo aparte para no crecer propiedades.html.
    if (!document.getElementById('px-cierre-js')) {
      var sc = document.createElement('script'); sc.id = 'px-cierre-js'; sc.src = 'propiedades-cierre.js'; sc.defer = true;
      document.body.appendChild(sc);
    }
    var selTipo = g('props-filter-tipo');
    if (selTipo) selTipo.innerHTML = C.tiposOptions('', { vacio: 'Todos los tipos' });
    var selOp = g('props-filter-op');
    if (selOp) selOp.innerHTML = C.listaOptions(C.data.operaciones, '', 'Todas las operaciones');
    var f = g('prop-form');
    if (f && f.elements['tipo']) f.elements['tipo'].innerHTML = C.tiposOptions('', { vacio: 'Seleccionar' });
    ['condicion', 'disposicion', 'orientacion'].forEach(function (k) {
      var el = f && f.elements[k]; if (!el) return;
      var lista = { condicion: C.data.condiciones, disposicion: C.data.disposiciones, orientacion: C.data.orientaciones }[k];
      el.innerHTML = C.listaOptions(lista, '', 'No indicado');
    });
    pintarCaract([]);
    pintarBadge();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
