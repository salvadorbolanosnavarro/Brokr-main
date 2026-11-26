// acm.js · Análisis comparativo de mercado (routers/acm.py).
// Tres vistas por hash: lista (#), captura (#nuevo) y mesa de trabajo (#a/<id>).
// Cada decisión del asesor (incluir, ajustes, estrategia, notas) se guarda en
// el servidor, que recalcula todo con la misma matemática del reporte: no hay
// una segunda copia del cálculo en el navegador.
(function () {
  'use strict';
  var esc = window.bkEsc, api = window.bkApi, toast = window.bkToast;
  var raiz = document.getElementById('acm-root');
  var S = { doc: null, tab: 'todos', abiertos: {}, enVuelo: false, pendiente: false, investigando: false, lista: null };
  var TIPOS = [['casa', 'Casa'], ['departamento', 'Departamento'], ['terreno', 'Terreno'], ['local', 'Local comercial'],
    ['oficina', 'Oficina'], ['bodega', 'Bodega'], ['otro', 'Otro']];
  var CONSERVACION = [['excelente', 'Excelente / como nuevo'], ['bueno', 'Bueno'], ['regular', 'Regular / requiere detalles'], ['remodelar', 'Para remodelar']];
  var GRUPOS = { activo: 'En venta', vendido: 'Vendido o retirado', bajas: 'Bajas o vencido' };
  var ORIGEN = { mercado: 'Portales', inventario: 'Tu inventario', bolsa: 'Bolsa Broquer', cierre: 'Cierre real', manual: 'Agregado a mano' };
  var ESTRATEGIAS = [['rapido', 'Venta rápida'], ['mercado', 'Precio de mercado'], ['aspiracional', 'Aspiracional']];
  var TICK = '<svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12l5 5L19 7"/></svg>';
  var ICO_ATRAS = '<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 18l-6-6 6-6"/></svg>';

  function loc() { return window.bkLocale ? window.bkLocale() : 'es-MX'; }
  function num(v) { var n = parseFloat(String(v == null ? '' : v).replace(/[^0-9.\-]/g, '')); return isFinite(n) ? n : null; }
  function dinero(v, moneda) {
    if (v == null || !isFinite(v)) return '—';
    var t = '$' + Math.round(v).toLocaleString(loc());
    return (!moneda || moneda === 'MXN') ? t : t + ' ' + moneda;
  }
  function m2(v) { return v ? Math.round(v).toLocaleString(loc()) + ' m²' : '—'; }
  function dist(c) {
    if (c.distancia_m == null) return '—';
    var t = c.distancia_m >= 1000 ? (c.distancia_m / 1000).toFixed(1) + ' km' : Math.round(c.distancia_m) + ' m';
    return c.precision_ubicacion === 'colonia' ? '≈ ' + t : t;
  }
  function fecha(iso) { if (!iso) return ''; var d = new Date(iso); return isNaN(d) ? '' : d.toLocaleDateString(loc(), { day: 'numeric', month: 'short', year: 'numeric' }); }
  function opts(lista, sel) { return lista.map(function (o) { return '<option value="' + o[0] + '"' + (o[0] === sel ? ' selected' : '') + '>' + esc(o[1]) + '</option>'; }).join(''); }
  function confianzaBadge(r) {
    var c = (r && r.confianza) || 'sin_datos';
    var cls = { alta: 'bk-badge--success', media: 'bk-badge--warn', baja: 'bk-badge--danger' }[c] || '';
    var txt = { alta: 'Confianza alta', media: 'Confianza media', baja: 'Confianza baja', sin_datos: 'Sin datos' }[c];
    return '<span class="bk-badge bk-badge--dot ' + cls + '">' + txt + '</span>';
  }

  // ── Lista ────────────────────────────────────────────────────────────────
  async function vistaLista() {
    raiz.innerHTML = '<div class="acm-barra"><p class="acm-sub">Analiza el mercado de una propiedad y preséntaselo al propietario con tu marca.</p>' +
      '<a class="bk-btn bk-btn--forest" href="#nuevo">Nuevo análisis</a></div><div id="acm-lista"><div class="bk-cargando">Cargando…</div></div>';
    var cont = document.getElementById('acm-lista');
    try { S.lista = await api('/acm'); } catch (e) { cont.innerHTML = '<div class="bk-alert bk-alert--error">' + esc(e.message) + '</div>'; return; }
    if (!S.lista.length) {
      cont.innerHTML = '<div class="bk-empty"><div class="bk-empty__title">Aún no tienes análisis</div>' +
        '<div class="bk-empty__text">Captura los datos de una propiedad y en segundos verás su competencia, lo que el mercado pagó y un rango de precio.</div>' +
        '<a class="bk-btn bk-btn--forest bk-empty__action" href="#nuevo">Crear el primero</a></div>';
      return;
    }
    cont.innerHTML = '<div class="acm-lista">' + S.lista.map(function (a) {
      var v = a.valor || {};
      return '<a class="bk-card bk-card--pad bk-card--raise bk-card--hover acm-item" href="#a/' + esc(a.id) + '">' +
        '<span class="bk-eyebrow">' + esc(fecha(a.updated_at)) + (a.propio ? '' : ' · De tu equipo') + '</span>' +
        '<span class="acm-item__t">' + esc(a.titulo || 'Análisis') + '</span>' +
        '<span class="acm-item__v">' + (a.precio_salida ? dinero(a.precio_salida, a.moneda) : (v.medio ? dinero(v.medio, a.moneda) : '—')) + '</span>' +
        '<span class="acm-sub">' + (v.bajo ? 'Rango ' + dinero(v.bajo, a.moneda) + ' – ' + dinero(v.alto, a.moneda) : 'Sin rango todavía') + '</span>' +
        '<span class="bk-cluster">' + confianzaBadge(a) +
        (a.estatus === 'presentado' ? '<span class="bk-chip bk-chip--info">Presentado</span>' : '<span class="bk-chip">Borrador</span>') +
        (a.vistas ? '<span class="bk-chip bk-chip--success">Abierto ' + a.vistas + (a.vistas === 1 ? ' vez' : ' veces') + '</span>' : '') +
        '</span></a>';
    }).join('') + '</div>';
  }

  // ── Captura ──────────────────────────────────────────────────────────────
  function campo(id, label, attrs) {
    return '<div class="bk-field"><label class="bk-label" for="' + id + '">' + label + '</label><input class="bk-input" id="' + id + '" ' + (attrs || '') + '/></div>';
  }
  async function vistaNuevo() {
    raiz.innerHTML = '<div class="acm-barra"><a class="bk-btn bk-btn--ghost bk-btn--sm" href="#">' + ICO_ATRAS + ' Mis análisis</a></div>' +
      '<form class="bk-card bk-card--pad bk-card--raise bk-stack" id="acm-nuevo" autocomplete="off">' +
      '<div class="acm-grid2">' +
      '<div class="bk-field"><label class="bk-label" for="n-tipo">Tipo de inmueble</label><select class="bk-select" id="n-tipo">' + opts(TIPOS, 'casa') + '</select></div>' +
      '<div class="bk-field"><span class="bk-label">Operación</span><div class="bk-seg" id="n-op"><button type="button" class="bk-seg__btn is-active" data-op="venta">Venta</button><button type="button" class="bk-seg__btn" data-op="renta">Renta</button></div></div>' +
      '</div>' +
      '<div class="bk-field acm-sugs"><label class="bk-label" for="n-colonia">Colonia</label><input class="bk-input" id="n-colonia" placeholder="Empieza a escribir la colonia" required/>' +
      '<div class="acm-sugs__lista" id="n-sugs" hidden></div></div>' +
      '<div class="acm-grid2">' + campo('n-ciudad', 'Ciudad', 'required') + campo('n-estado', 'Estado') + '</div>' +
      campo('n-dir', 'Dirección o referencia (opcional, aparece en el reporte)', 'maxlength="160"') +
      '<div class="acm-grid4">' + campo('n-m2c', 'm² construcción', 'inputmode="decimal"') + campo('n-m2t', 'm² terreno', 'inputmode="decimal"') +
      campo('n-rec', 'Recámaras', 'inputmode="numeric"') + campo('n-ban', 'Baños', 'inputmode="decimal"') +
      campo('n-est', 'Estacionamientos', 'inputmode="numeric"') + campo('n-ant', 'Antigüedad (años)', 'inputmode="numeric"') +
      '<div class="bk-field"><label class="bk-label" for="n-cons">Conservación</label><select class="bk-select" id="n-cons">' + opts(CONSERVACION, 'bueno') + '</select></div>' +
      campo('n-esperado', 'Precio que quiere el propietario', 'inputmode="decimal"') + '</div>' +
      '<p class="bk-hint">Mientras más datos captures, mejor se eligen y ajustan los comparables. Sólo la ciudad y los m² son obligatorios.</p>' +
      '<div class="bk-cluster" style="justify-content:flex-end"><button class="bk-btn bk-btn--forest bk-btn--lg" type="submit" id="n-ir">Analizar mercado</button></div>' +
      '</form>';
    var sel = { lat: null, lng: null, op: 'venta', propiedad_id: null, contacto_id: null };
    var g = function (id) { return document.getElementById(id); };
    g('n-op').addEventListener('click', function (e) {
      var b = e.target.closest('[data-op]'); if (!b) return;
      sel.op = b.dataset.op;
      g('n-op').querySelectorAll('.bk-seg__btn').forEach(function (x) { x.classList.toggle('is-active', x === b); });
    });
    var timer = null;
    g('n-colonia').addEventListener('input', function () {
      sel.lat = sel.lng = null;
      clearTimeout(timer);
      var txt = this.value.trim();
      if (txt.length < 3) { g('n-sugs').hidden = true; return; }
      timer = setTimeout(async function () {
        try {
          var d = await api('/api/colonias?texto=' + encodeURIComponent(txt) + '&ciudad=' + encodeURIComponent(g('n-ciudad').value) + '&pais=' + (window.bkPais ? window.bkPais() : 'MX'));
          var cols = (d && d.colonias) || [];
          g('n-sugs').innerHTML = cols.map(function (c, i) { return '<button type="button" class="acm-sugs__op" data-i="' + i + '">' + esc(c.display || c.nombre) + '</button>'; }).join('');
          g('n-sugs').hidden = !cols.length;
          g('n-sugs').onclick = function (e) {
            var b = e.target.closest('[data-i]'); if (!b) return;
            var c = cols[+b.dataset.i];
            g('n-colonia').value = c.nombre || '';
            if (c.ciudad) g('n-ciudad').value = c.ciudad;
            if (c.estado) g('n-estado').value = c.estado;
            sel.lat = c.latitud || null; sel.lng = c.longitud || null;
            g('n-sugs').hidden = true;
          };
        } catch (e) { g('n-sugs').hidden = true; }
      }, 350);
    });
    // Precarga desde un inmueble del inventario: acm.html?propiedad=<id>
    var qs = new URLSearchParams(location.search);
    sel.contacto_id = qs.get('contacto');
    if (qs.get('propiedad')) {
      try {
        var p = (await window.bkRest('propiedades?id=eq.' + encodeURIComponent(qs.get('propiedad')) + '&select=id,tipo,operacion,colonia,ciudad,estado,calle,num_exterior,m2_construccion,m2_terreno,recamaras,banos,estacionamientos,antiguedad,precio,lat,lng'))[0];
        if (p) {
          sel.propiedad_id = p.id; sel.lat = p.lat || null; sel.lng = p.lng || null;
          g('n-tipo').value = TIPOS.some(function (t) { return t[0] === p.tipo; }) ? p.tipo : 'otro';
          if (String(p.operacion || '').indexOf('renta') === 0) g('n-op').querySelector('[data-op="renta"]').click();
          [['n-colonia', p.colonia], ['n-ciudad', p.ciudad], ['n-estado', p.estado], ['n-m2c', p.m2_construccion], ['n-m2t', p.m2_terreno],
            ['n-rec', p.recamaras], ['n-ban', p.banos], ['n-est', p.estacionamientos], ['n-ant', p.antiguedad], ['n-esperado', p.precio],
            ['n-dir', [p.calle, p.num_exterior].filter(Boolean).join(' ')]].forEach(function (x) { if (x[1] != null && x[1] !== '') g(x[0]).value = x[1]; });
        }
      } catch (e) { /* sin precarga: el asesor captura a mano */ }
    }
    // Precarga que deja el asistente del chat (acción llenar_acm).
    try {
      var chat = JSON.parse(sessionStorage.getItem('shaark_acm') || 'null');
      sessionStorage.removeItem('shaark_acm');
      if (chat) {
        var tipo = chat.tipo_inmueble || chat.tipo;
        if (TIPOS.some(function (t) { return t[0] === tipo; })) g('n-tipo').value = tipo;
        if (String(chat.operacion || '').indexOf('renta') === 0) g('n-op').querySelector('[data-op="renta"]').click();
        [['n-colonia', chat.colonia], ['n-ciudad', chat.ciudad], ['n-estado', chat.estado], ['n-m2c', chat.m2_construccion],
          ['n-m2t', chat.m2_terreno], ['n-rec', chat.recamaras], ['n-ban', chat.banos], ['n-est', chat.estacionamientos],
          ['n-ant', chat.antiguedad]].forEach(function (x) { if (x[1] != null && x[1] !== '' && x[1] !== 0) g(x[0]).value = x[1]; });
      }
    } catch (e) { /* sin precarga */ }
    g('acm-nuevo').addEventListener('submit', async function (e) {
      e.preventDefault();
      var boton = g('n-ir');
      boton.disabled = true; boton.textContent = 'Analizando…';
      var sujeto = {
        tipo: g('n-tipo').value, operacion: sel.op, colonia: g('n-colonia').value.trim(), ciudad: g('n-ciudad').value.trim(),
        estado: g('n-estado').value.trim(), direccion: g('n-dir').value.trim(), lat: sel.lat, lng: sel.lng,
        m2_construccion: num(g('n-m2c').value), m2_terreno: num(g('n-m2t').value), recamaras: num(g('n-rec').value),
        banos: num(g('n-ban').value), estacionamientos: num(g('n-est').value), antiguedad: num(g('n-ant').value),
        conservacion: g('n-cons').value, precio_esperado: num(g('n-esperado').value),
        propiedad_id: sel.propiedad_id, contacto_id: sel.contacto_id
      };
      try {
        var doc = await api('/acm', { method: 'POST', json: { sujeto: sujeto } });
        S.doc = doc; S.investigarAlAbrir = doc.faltan_comparables;
        location.hash = '#a/' + doc.id;
      } catch (err) {
        toast(err.message); boton.disabled = false; boton.textContent = 'Analizar mercado';
      }
    });
  }

  // ── Mesa de trabajo ──────────────────────────────────────────────────────
  async function vistaDoc(id) {
    if (!S.doc || S.doc.id !== id) {
      raiz.innerHTML = '<div class="bk-cargando">Cargando…</div>';
      try { S.doc = await api('/acm/' + encodeURIComponent(id)); } catch (e) { raiz.innerHTML = '<div class="bk-alert bk-alert--error">' + esc(e.message) + '</div>'; return; }
      S.abiertos = {}; S.tab = 'todos';
    }
    pintarDoc();
    if (S.investigarAlAbrir) { S.investigarAlAbrir = false; investigar(); }
  }

  function filaComp(c, i, moneda) {
    var abierto = !!S.abiertos[c.id];
    var titulo = c.titulo || ((c.tipo || 'Inmueble') + ' en ' + (c.colonia || 'la zona'));
    var link = c.url ? '<a href="' + esc(c.url) + '" target="_blank" rel="noopener">' + esc(titulo) + '</a>' : esc(titulo);
    var chips = '<span class="bk-chip">' + esc(GRUPOS[c.grupo] || '') + '</span>' +
      (c.atipico ? '<span class="bk-chip bk-chip--warn">Precio atípico</span>' : '') +
      (c.bajas_precio ? '<span class="bk-chip bk-chip--warn">Bajó de precio</span>' : '');
    var precio = c.grupo === 'vendido' && c.precio_cierre ? c.precio_cierre : c.precio;
    var det = '';
    if (abierto) {
      det = '<div class="acm-comp__det">' +
        '<div class="acm-sub">' + esc(ORIGEN[c.origen] || '') + (c.portal && c.origen === 'mercado' ? ' · ' + esc(c.portal) : '') +
        (c.primera_vez ? ' · visto desde ' + esc(fecha(c.primera_vez)) : '') + (c.dias_mercado != null ? ' · ' + c.dias_mercado + ' días en el mercado' : '') +
        ' · similitud ' + Math.round(c.similitud || 0) + '/100' + (c.motivo ? ' · ' + esc(c.motivo) : '') + '</div>' +
        '<div class="acm-sub">' + [c.recamaras != null ? c.recamaras + ' rec' : '', c.banos != null ? c.banos + ' baños' : '', c.estacionamientos != null ? c.estacionamientos + ' est' : '',
          c.m2_terreno ? m2(c.m2_terreno) + ' terreno' : '', c.m2_construccion ? m2(c.m2_construccion) + ' const.' : '', c.antiguedad != null ? c.antiguedad + ' años' : ''].filter(Boolean).join(' · ') + '</div>' +
        '<div class="bk-label">Ajustes a su precio por m²</div>' +
        (c.ajustes || []).map(function (a, j) {
          return '<div class="acm-aj"><input class="bk-input" data-aj-concepto="' + j + '" data-c="' + esc(c.id) + '" value="' + esc(a.concepto) + '"' + (a.auto ? ' readonly' : '') + ' title="' + esc(a.detalle || '') + '"/>' +
            '<div class="bk-input-affix"><input class="bk-input" inputmode="decimal" data-aj-pct="' + j + '" data-c="' + esc(c.id) + '" value="' + a.pct + '"/><span class="bk-input-affix__suffix">%</span></div>' +
            '<button class="bk-btn bk-btn--quiet bk-btn--sm" type="button" data-aj-quitar="' + j + '" data-c="' + esc(c.id) + '">Quitar</button></div>';
        }).join('') +
        '<div class="bk-cluster"><button class="bk-btn bk-btn--ghost bk-btn--sm" type="button" data-aj-nuevo="' + esc(c.id) + '">Agregar ajuste</button>' +
        '<span class="acm-sub">Total ' + (c.ajuste_total_pct > 0 ? '+' : '') + (c.ajuste_total_pct || 0) + '% → ' + dinero(c.precio_m2_ajustado, moneda) + '/m²</span></div>' +
        '<input class="bk-input" data-nota="' + esc(c.id) + '" value="' + esc(c.nota || '') + '" placeholder="Nota interna sobre este comparable" maxlength="300"/>' +
        (c.origen === 'manual' ? '<div><button class="bk-btn bk-btn--danger bk-btn--sm" type="button" data-borrar-comp="' + esc(c.id) + '">Eliminar comparable</button></div>' : '') +
        '</div>';
    }
    return '<div class="acm-comp' + (c.incluido ? '' : ' acm-comp--fuera') + '">' +
      '<div class="acm-comp__fila">' +
      '<label class="bk-check"><input type="checkbox" data-incluir="' + esc(c.id) + '"' + (c.incluido ? ' checked' : '') + (c.precio_m2_ajustado ? '' : ' disabled') + ' aria-label="Incluir en el análisis"/><span class="bk-check__box">' + TICK + '</span></label>' +
      '<div style="min-width:0"><div class="acm-comp__t">' + link + '</div><div class="acm-comp__s">' + esc(c.colonia || '') + ' ' + chips + '</div>' +
      '<div class="acm-movil">' + dinero(precio, moneda) + ' · ' + m2(c.superficie) + ' · ' + dinero(c.precio_m2_ajustado, moneda) + '/m² aj. · ' + dist(c) + '</div></div>' +
      '<div class="acm-comp__m">' + dinero(precio, moneda) + '<small>precio</small></div>' +
      '<div class="acm-comp__m">' + m2(c.superficie) + '<small>superficie</small></div>' +
      '<div class="acm-comp__m">' + dinero(c.precio_m2, moneda) + '<small>$/m²</small></div>' +
      '<div class="acm-comp__m">' + dinero(c.precio_m2_ajustado, moneda) + '<small>$/m² ajustado</small></div>' +
      '<div class="acm-comp__m">' + dist(c) + '<small>distancia</small></div>' +
      '<button class="bk-btn bk-btn--quiet bk-btn--sm" type="button" data-abrir="' + esc(c.id) + '">' + (abierto ? 'Cerrar' : 'Detalle') + '</button>' +
      '</div>' + det + '</div>';
  }

  function pintarDoc() {
    var d = S.doc, r = d.resultado || {}, s = d.sujeto || {}, e = d.estrategia || {}, v = r.valor || {}, pm2 = r.precio_m2 || {};
    var moneda = r.moneda || s.moneda || 'MXN';
    var comps = d.comparables || [];
    var conteo = { todos: comps.length, activo: 0, vendido: 0, bajas: 0 };
    comps.forEach(function (c) { conteo[c.grupo] = (conteo[c.grupo] || 0) + 1; });
    var visibles = comps.filter(function (c) { return S.tab === 'todos' || c.grupo === S.tab; });
    var comp = r.comparacion;
    var esperado = s.precio_esperado;
    var m = r.mercado || {};
    var scroll = window.scrollY;

    var html = '<div class="acm-barra"><a class="bk-btn bk-btn--ghost bk-btn--sm" href="#">' + ICO_ATRAS + ' Mis análisis</a>' +
      '<span class="bk-cluster">' + (d.vistas ? '<span class="bk-chip bk-chip--success">El propietario lo abrió ' + d.vistas + (d.vistas === 1 ? ' vez' : ' veces') + (d.ultima_vista ? ' · ' + esc(fecha(d.ultima_vista)) : '') + '</span>' : '') +
      '<span class="acm-sub" id="acm-estado-guardado">' + (S.enVuelo ? 'Guardando…' : 'Guardado') + '</span></span></div>' +
      '<h1 style="font-size:var(--fs-h2);margin-bottom:var(--sp-1)">' + esc(d.titulo || 'Análisis') + '</h1>' +
      '<p class="acm-sub" style="margin-bottom:var(--sp-5)">' + esc([s.direccion, s.colonia, s.ciudad].filter(Boolean).join(' · ')) + '</p>';

    if (comp) {
      html += '<div class="bk-alert bk-alert--info" style="margin-bottom:var(--sp-4)">Actualizado con el mercado de hoy: ' +
        (comp.cambio_pct != null ? 'el centro del rango ' + (comp.cambio_pct >= 0 ? 'subió ' : 'bajó ') + Math.abs(comp.cambio_pct) + '%' : 'sin cambio comparable en el valor') +
        ' · ' + comp.comparables_nuevos + ' comparables nuevos (sin incluir, revísalos)' +
        (comp.se_vendieron_o_retiraron ? ' · ' + comp.se_vendieron_o_retiraron + ' de tus comparables ya se vendieron o retiraron' : '') + '.</div>';
    }
    if (S.investigando) {
      html += '<div class="bk-card bk-card--pad acm-cargando" style="margin-bottom:var(--sp-4)"><span class="bk-spinner"></span><div><strong>Buscando más comparables en portales…</strong>' +
        '<div class="acm-sub">Puede tardar hasta un minuto. Puedes seguir trabajando; lo nuevo se agrega solo.</div></div></div>';
    } else if (d.faltan_comparables) {
      html += '<div class="bk-alert bk-alert--warn" style="margin-bottom:var(--sp-4)">Hay pocos comparables en esta zona. ' +
        '<button class="bk-btn bk-btn--ghost bk-btn--sm" type="button" data-accion="investigar">Buscar más en portales</button></div>';
    }

    html += '<div class="acm-resumen"><div class="bk-card bk-card--pad bk-card--raise">' +
      '<div class="bk-cluster" style="justify-content:space-between"><span class="bk-eyebrow">Rango de mercado</span>' + confianzaBadge(r) + '</div>' +
      '<div class="acm-rango"><div><div class="acm-rango__l">Parte baja</div><div class="acm-rango__v">' + dinero(v.bajo, moneda) + '</div></div>' +
      '<div><div class="acm-rango__l">Centro</div><div class="acm-rango__v acm-rango__v--med">' + dinero(v.medio, moneda) + '</div></div>' +
      '<div><div class="acm-rango__l">Parte alta</div><div class="acm-rango__v">' + dinero(v.alto, moneda) + '</div></div></div>' +
      '<p class="acm-sub" style="margin-top:var(--sp-4)">' + esc(r.razon_confianza || '') + ' Precio por m² ajustado: ' + dinero(pm2.p25, moneda) + ' a ' + dinero(pm2.p75, moneda) +
      ' sobre ' + m2(r.superficie) + ' de ' + (r.base_superficie === 'terreno' ? 'terreno' : 'construcción') + '.</p>' +
      (esperado ? '<p class="acm-sub">El propietario espera ' + dinero(esperado, moneda) + (v.medio ? ' (' + (esperado >= v.medio ? '+' : '') + Math.round((esperado / v.medio - 1) * 100) + '% vs. el centro del mercado)' : '') + '.</p>' : '') +
      '<div class="acm-grid2" style="margin-top:var(--sp-3)">' +
      '<div class="bk-field"><label class="bk-label" for="d-desc">Margen de negociación</label><div class="bk-input-affix"><input class="bk-input" id="d-desc" inputmode="decimal" value="' + ((r.descuento || {}).pct != null ? r.descuento.pct : '') + '"/><span class="bk-input-affix__suffix">%</span></div>' +
      '<div class="bk-hint">' + ((r.descuento || {}).fuente === 'cierres' ? 'Calculado con ' + r.descuento.n + ' cierres reales de tu cuenta.' : ((r.descuento || {}).fuente === 'asesor' ? 'Definido por ti.' : 'Valor típico; se calibra solo con tus cierres.')) + '</div></div>' +
      '<div class="bk-field"><label class="bk-label" for="d-gen">Ajuste general a la propiedad</label><div class="bk-input-affix"><input class="bk-input" id="d-gen" inputmode="decimal" value="' + (s.ajuste_general_pct || 0) + '"/><span class="bk-input-affix__suffix">%</span></div>' +
      '<div class="bk-hint">Vista, acabados, ubicación dentro de la colonia…</div></div></div>' +
      '</div>' +
      '<div class="bk-card bk-card--pad bk-card--raise"><span class="bk-eyebrow">Mercado de la zona</span>' +
      '<div class="bk-datos" style="margin-top:var(--sp-3)">' +
      [['En venta', m.en_venta], ['Vendidos o retirados', m.vendidos], ['Con bajas o vencidos', m.con_bajas_o_vencidos],
        ['Días publicados (mediana)', m.dias_mercado_mediana != null ? Math.round(m.dias_mercado_mediana) : null],
        ['$/m² de oferta', m.precio_m2_oferta_mediana ? dinero(m.precio_m2_oferta_mediana, moneda) : null],
        ['$/m² vendidos', m.precio_m2_vendidos_mediana ? dinero(m.precio_m2_vendidos_mediana, moneda) : null]].map(function (x) {
        return '<div class="bk-dato"><div class="bk-dato__lbl">' + x[0] + '</div><div class="bk-dato__val">' + (x[1] == null ? '—' : esc(x[1])) + '</div></div>';
      }).join('') + '</div>' +
      '<details style="margin-top:var(--sp-4)"><summary class="bk-label">Características de la propiedad</summary><div class="acm-grid3" style="margin-top:var(--sp-3)">' +
      [['m2_construccion', 'm² construcción'], ['m2_terreno', 'm² terreno'], ['recamaras', 'Recámaras'], ['banos', 'Baños'], ['estacionamientos', 'Estacionamientos'], ['antiguedad', 'Antigüedad']].map(function (x) {
        return '<div class="bk-field"><label class="bk-label" for="s-' + x[0] + '">' + x[1] + '</label><input class="bk-input" inputmode="decimal" id="s-' + x[0] + '" data-sujeto="' + x[0] + '" value="' + (s[x[0]] != null ? s[x[0]] : '') + '"/></div>';
      }).join('') +
      '<div class="bk-field"><label class="bk-label" for="s-cons">Conservación</label><select class="bk-select" id="s-cons" data-sujeto="conservacion">' + opts(CONSERVACION, s.conservacion || 'bueno') + '</select></div>' +
      '</div></details></div></div>';

    html += '<div class="acm-sec"><div class="acm-barra" style="margin-bottom:0"><h2 style="margin:0">Comparables <span class="acm-sub">' + (r.n_incluidos || 0) + ' incluidos de ' + comps.length + '</span></h2>' +
      '<span class="bk-cluster"><button class="bk-btn bk-btn--ghost bk-btn--sm" type="button" data-accion="agregar">Agregar comparable</button>' +
      '<button class="bk-btn bk-btn--ghost bk-btn--sm" type="button" data-accion="investigar"' + (S.investigando ? ' disabled' : '') + '>Buscar más en portales</button></span></div>' +
      '<div class="bk-tabs acm-tabs" role="tablist">' + [['todos', 'Todos'], ['activo', 'En venta'], ['vendido', 'Vendidos o retirados'], ['bajas', 'Bajas o vencidos']].map(function (t) {
        return '<button class="bk-tab' + (S.tab === t[0] ? ' is-active' : '') + '" type="button" role="tab" data-tab="' + t[0] + '">' + t[1] + ' <span class="bk-tab__n">' + (conteo[t[0]] || 0) + '</span></button>';
      }).join('') + '</div>' +
      (visibles.length ? visibles.map(function (c, i) { return filaComp(c, i, moneda); }).join('') :
        '<div class="bk-empty"><div class="bk-empty__title">Sin comparables en este grupo</div><div class="bk-empty__text">Busca más en portales o agrega uno que conozcas.</div></div>') +
      '</div>';

    var precios = e.precios || {}, dias = e.dias || {};
    html += '<div class="acm-sec"><h2>Estrategia de precio</h2><div class="acm-grid3">' + ESTRATEGIAS.map(function (x) {
      return '<div class="acm-est' + (e.elegida === x[0] ? ' is-on' : '') + '" data-elegir="' + x[0] + '"><div class="acm-est__n">' + x[1] + '</div>' +
        '<div class="bk-input-affix" style="margin:var(--sp-2) 0"><input class="bk-input" inputmode="decimal" data-precio="' + x[0] + '" value="' + (precios[x[0]] ? Math.round(precios[x[0]]) : '') + '"/></div>' +
        '<div class="acm-sub">' + (dias[x[0]] ? 'Referencia: ~' + dias[x[0]] + ' días en el mercado' : 'Sin referencia de tiempo todavía') + '</div></div>';
    }).join('') + '</div>' +
      '<div class="bk-cluster" style="margin-top:var(--sp-3)"><label class="bk-check"><input type="checkbox" id="e-propio"' + (e.elegida === 'propio' ? ' checked' : '') + '/><span class="bk-check__box">' + TICK + '</span> Otro precio acordado</label>' +
      '<div class="bk-input-affix"' + (e.elegida === 'propio' ? '' : ' hidden') + ' id="e-propio-wrap"><input class="bk-input" inputmode="decimal" id="e-propio-precio" value="' + (e.elegida === 'propio' && e.precio_salida ? Math.round(e.precio_salida) : '') + '"/></div></div></div>';

    html += '<div class="acm-sec acm-grid2"><div class="bk-field"><label class="bk-label" for="d-nota">Comentario para el propietario (aparece en el reporte)</label>' +
      '<textarea class="bk-textarea" id="d-nota" rows="4" maxlength="3000">' + esc(d.nota_propietario || '') + '</textarea></div>' +
      '<div class="bk-field"><label class="bk-label" for="d-internas">Notas internas (sólo tú las ves)</label>' +
      '<textarea class="bk-textarea" id="d-internas" rows="4" maxlength="3000">' + esc(d.notas_internas || '') + '</textarea></div></div>';

    html += '<div class="acm-sec bk-card bk-card--pad bk-card--raise"><h2>Presentar al propietario</h2>' +
      '<div class="bk-cluster"><button class="bk-btn bk-btn--forest" type="button" data-accion="pdf">Descargar PDF</button>' +
      '<label class="bk-switch"><input type="checkbox" id="d-liga"' + (d.liga_activa ? ' checked' : '') + '/><span class="bk-switch__track"></span> Liga para compartir</label></div>' +
      (d.liga_activa && d.liga_url ? '<div class="acm-liga" style="margin-top:var(--sp-3)"><input class="bk-input" readonly value="' + esc(d.liga_url) + '" id="d-liga-url"/>' +
        '<button class="bk-btn bk-btn--ghost bk-btn--sm" type="button" data-accion="copiar">Copiar</button>' +
        '<a class="bk-btn bk-btn--ghost bk-btn--sm" target="_blank" rel="noopener" href="' + esc(d.liga_url) + '">Ver como propietario</a>' +
        '<a class="bk-btn bk-btn--forest bk-btn--sm" target="_blank" rel="noopener" href="https://wa.me/?text=' + encodeURIComponent('Te comparto el análisis de mercado de tu propiedad: ' + d.liga_url) + '">Enviar por WhatsApp</a></div>' +
        '<p class="bk-hint">Te avisamos cuando el propietario la abra. Puedes desactivarla en cualquier momento.</p>' : '') +
      '<div class="bk-divider" style="margin:var(--sp-4) 0"></div>' +
      '<div class="bk-cluster"><button class="bk-btn bk-btn--ghost" type="button" data-accion="actualizar">Actualizar con el mercado de hoy</button>' +
      '<button class="bk-btn bk-btn--quiet" type="button" data-accion="borrar">Eliminar análisis</button></div>' +
      '<p class="bk-hint">Actualizar crea una versión nueva con datos frescos y te dice qué cambió, ideal para revisar el precio si la propiedad no se ha vendido.</p></div>';

    raiz.innerHTML = html;
    window.scrollTo(0, scroll);
  }

  // ── Guardar (cola de un vuelo a la vez) ──────────────────────────────────
  function cuerpo() {
    var d = S.doc;
    // Sólo viajan los precios de estrategia que el asesor editó: los demás
    // siguen al rango cada vez que cambia el análisis.
    var e = d.estrategia || {}, editados = e.editados || [], precios = {};
    editados.forEach(function (k) { if (e.precios && e.precios[k]) precios[k] = e.precios[k]; });
    var estrategia = { elegida: e.elegida, precio_salida: e.precio_salida, precios: precios };
    return { sujeto: d.sujeto, comparables: d.comparables, estrategia: estrategia, nota_propietario: d.nota_propietario,
      notas_internas: d.notas_internas, descuento_pct: S.descuentoNuevo };
  }
  async function guardar() {
    if (S.enVuelo) { S.pendiente = true; return; }
    S.enVuelo = true;
    var est = document.getElementById('acm-estado-guardado'); if (est) est.textContent = 'Guardando…';
    var b = cuerpo(); S.descuentoNuevo = undefined;
    try {
      var nuevo = await api('/acm/' + encodeURIComponent(S.doc.id), { method: 'PUT', json: b });
      S.enVuelo = false;
      if (S.pendiente) { S.pendiente = false; guardar(); return; }
      S.doc = nuevo;
      pintarDoc();
    } catch (e) {
      S.enVuelo = false; S.pendiente = false;
      toast('No se guardó: ' + e.message);
      if (est) est.textContent = 'Sin guardar';
    }
  }
  function compPorId(id) { return (S.doc.comparables || []).find(function (c) { return c.id === id; }); }

  async function investigar() {
    if (S.investigando) return;
    S.investigando = true; pintarDoc();
    try {
      var r = await api('/acm/' + encodeURIComponent(S.doc.id) + '/investigar', { method: 'POST' });
      S.investigando = false;
      S.doc = r; pintarDoc();
      var inv = r.investigacion || {};
      toast(inv.agregados ? 'Se agregaron ' + inv.agregados + ' comparables nuevos.' : 'No aparecieron comparables nuevos en portales.');
    } catch (e) { S.investigando = false; pintarDoc(); toast(e.message); }
  }

  async function descargarPdf(boton) {
    boton.disabled = true; boton.textContent = 'Generando…';
    try {
      var tok = window.brokrSb && window.brokrSb.ensureToken ? await window.brokrSb.ensureToken() : '';
      var r = await fetch((window.API_BASE || 'https://api.broquer.app') + '/acm/' + encodeURIComponent(S.doc.id) + '/pdf', { headers: tok ? { Authorization: 'Bearer ' + tok } : {} });
      if (!r.ok) { var err = {}; try { err = await r.json(); } catch (x) { /* sin detalle */ } throw new Error(err.detail || 'No se pudo generar el PDF.'); }
      var blob = await r.blob();
      var nombre = (/filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '') || [])[1] || 'Analisis_de_mercado.pdf';
      if (window.broquerDeliverBlob) await window.broquerDeliverBlob(blob, nombre, { type: 'application/pdf', title: 'Análisis comparativo listo', text: 'Análisis comparativo de mercado' });
      else { var u = URL.createObjectURL(blob); var a = document.createElement('a'); a.href = u; a.download = nombre; a.click(); setTimeout(function () { URL.revokeObjectURL(u); }, 3000); }
    } catch (e) { toast(e.message); }
    boton.disabled = false; boton.textContent = 'Descargar PDF';
  }

  // ── Eventos de la mesa de trabajo (delegados) ────────────────────────────
  raiz.addEventListener('click', async function (e) {
    if (!S.doc || !location.hash.startsWith('#a/')) return;
    var t = e.target;
    var b;
    if ((b = t.closest('[data-tab]'))) { S.tab = b.dataset.tab; pintarDoc(); return; }
    if ((b = t.closest('[data-abrir]'))) { S.abiertos[b.dataset.abrir] = !S.abiertos[b.dataset.abrir]; pintarDoc(); return; }
    if ((b = t.closest('[data-aj-quitar]'))) {
      var c = compPorId(b.dataset.c), a = c.ajustes[+b.dataset.ajQuitar];
      if (a.auto) { a.pct = 0; a.auto = false; } else { c.ajustes.splice(+b.dataset.ajQuitar, 1); }
      guardar(); return;
    }
    if ((b = t.closest('[data-aj-nuevo]'))) {
      var cc = compPorId(b.dataset.ajNuevo); cc.ajustes = cc.ajustes || [];
      cc.ajustes.push({ concepto: 'Otro ajuste', pct: 0, auto: false }); pintarDoc(); return;
    }
    if ((b = t.closest('[data-borrar-comp]'))) {
      S.doc.comparables = S.doc.comparables.filter(function (x) { return x.id !== b.dataset.borrarComp; }); guardar(); return;
    }
    if ((b = t.closest('[data-elegir]')) && !t.closest('input')) {
      S.doc.estrategia.elegida = b.dataset.elegir; guardar(); return;
    }
    if ((b = t.closest('[data-accion]'))) {
      var acc = b.dataset.accion;
      if (acc === 'investigar') investigar();
      else if (acc === 'agregar') abrirModal();
      else if (acc === 'pdf') descargarPdf(b);
      else if (acc === 'copiar') { var inp = document.getElementById('d-liga-url'); try { await navigator.clipboard.writeText(inp.value); toast('Liga copiada.'); } catch (x) { inp.select(); } }
      else if (acc === 'actualizar') {
        b.disabled = true; b.textContent = 'Actualizando…';
        try { var nuevo = await api('/acm/' + encodeURIComponent(S.doc.id) + '/actualizar', { method: 'POST' }); S.doc = nuevo; location.hash = '#a/' + nuevo.id; toast('Versión nueva creada con el mercado de hoy.'); }
        catch (x) { toast(x.message); b.disabled = false; b.textContent = 'Actualizar con el mercado de hoy'; }
      } else if (acc === 'borrar') {
        if (!confirm('¿Eliminar este análisis? La liga compartida dejará de funcionar.')) return;
        try { await api('/acm/' + encodeURIComponent(S.doc.id), { method: 'DELETE' }); S.doc = null; location.hash = ''; } catch (x) { toast(x.message); }
      }
    }
  });

  raiz.addEventListener('change', async function (e) {
    if (!S.doc || !location.hash.startsWith('#a/')) return;
    var t = e.target, c;
    if (t.dataset.incluir) { c = compPorId(t.dataset.incluir); c.incluido = t.checked; guardar(); return; }
    if (t.dataset.ajPct !== undefined) { c = compPorId(t.dataset.c); var a = c.ajustes[+t.dataset.ajPct]; a.pct = num(t.value) || 0; a.auto = false; guardar(); return; }
    if (t.dataset.ajConcepto !== undefined) { c = compPorId(t.dataset.c); c.ajustes[+t.dataset.ajConcepto].concepto = t.value.trim() || 'Ajuste'; guardar(); return; }
    if (t.dataset.nota !== undefined) { c = compPorId(t.dataset.nota); c.nota = t.value.trim(); guardar(); return; }
    if (t.dataset.sujeto) { S.doc.sujeto[t.dataset.sujeto] = t.tagName === 'SELECT' ? t.value : num(t.value); guardar(); return; }
    if (t.dataset.precio) {
      var e2 = S.doc.estrategia, k = t.dataset.precio; e2.precios = e2.precios || {}; e2.editados = e2.editados || [];
      e2.precios[k] = num(t.value); e2.elegida = k;
      if (e2.precios[k]) { if (e2.editados.indexOf(k) < 0) e2.editados.push(k); } else { e2.editados = e2.editados.filter(function (x) { return x !== k; }); }
      guardar(); return;
    }
    if (t.id === 'e-propio') {
      S.doc.estrategia.elegida = t.checked ? 'propio' : 'mercado';
      if (t.checked) { document.getElementById('e-propio-wrap').hidden = false; document.getElementById('e-propio-precio').focus(); return; }
      guardar(); return;
    }
    if (t.id === 'e-propio-precio') { S.doc.estrategia.elegida = 'propio'; S.doc.estrategia.precio_salida = num(t.value); guardar(); return; }
    if (t.id === 'd-desc') { S.descuentoNuevo = Math.max(0, Math.min(30, num(t.value) || 0)); guardar(); return; }
    if (t.id === 'd-gen') { S.doc.sujeto.ajuste_general_pct = num(t.value) || 0; guardar(); return; }
    if (t.id === 'd-nota') { S.doc.nota_propietario = t.value; guardar(); return; }
    if (t.id === 'd-internas') { S.doc.notas_internas = t.value; guardar(); return; }
    if (t.id === 'd-liga') {
      try {
        var r = await api('/acm/' + encodeURIComponent(S.doc.id) + '/liga', { method: 'POST', json: { activa: t.checked } });
        S.doc.liga_activa = r.liga_activa; S.doc.liga_url = r.liga_url; pintarDoc();
      } catch (x) { toast(x.message); t.checked = !t.checked; }
    }
  });

  // ── Modal: comparable agregado a mano ────────────────────────────────────
  var modal = document.getElementById('acm-modal');
  function abrirModal() { document.getElementById('acm-form-comp').reset(); modal.classList.add('is-open'); modal.setAttribute('aria-hidden', 'false'); document.getElementById('mc-titulo').focus(); }
  function cerrarModal() { modal.classList.remove('is-open'); modal.setAttribute('aria-hidden', 'true'); }
  modal.addEventListener('click', function (e) { if (e.target === modal || e.target.closest('[data-cerrar]')) cerrarModal(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && modal.classList.contains('is-open')) cerrarModal(); });
  document.getElementById('acm-form-comp').addEventListener('submit', function (e) {
    e.preventDefault();
    var g = function (id) { return document.getElementById(id).value; };
    var s = S.doc.sujeto, grupo = g('mc-grupo');
    var c = {
      id: 'manual-' + Date.now().toString(36), origen: 'manual', grupo: grupo, titulo: g('mc-titulo').trim(),
      tipo: s.tipo, operacion: s.operacion, moneda: s.moneda || 'MXN', colonia: s.colonia, ciudad: s.ciudad,
      precio: num(g('mc-precio')), m2_construccion: num(g('mc-m2c')), m2_terreno: num(g('mc-m2t')),
      recamaras: num(g('mc-rec')), banos: num(g('mc-ban')), estacionamientos: num(g('mc-est')),
      distancia_m: num(g('mc-dist')), dias_mercado: num(g('mc-dias')), url: g('mc-url').trim() || null,
      nota: g('mc-nota').trim(), incluido: true, ajustes: [], estatus: grupo === 'vendido' ? 'retirado' : 'activo'
    };
    if (grupo === 'vendido') c.precio_cierre = c.precio;
    if (!c.precio) { toast('Indica el precio.'); return; }
    S.doc.comparables.push(c); cerrarModal(); guardar();
  });

  // ── Ruteo ────────────────────────────────────────────────────────────────
  function ruta() {
    var h = location.hash || '';
    if (h === '#nuevo') return vistaNuevo();
    var m = /^#a\/([0-9a-f-]{36})$/.exec(h);
    if (m) return vistaDoc(m[1]);
    S.doc = null;
    return vistaLista();
  }
  window.addEventListener('hashchange', ruta);
  ruta();
})();
