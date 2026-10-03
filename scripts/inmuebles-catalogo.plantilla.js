// ─────────────────────────────────────────────────────────────────────────
// inmuebles-catalogo.js · Catálogo único de inmuebles (tipos, operaciones,
// características) + helpers de presentación.
//
// ARCHIVO GENERADO: no lo edites a mano. La fuente es
// core/catalogo_inmuebles.py; regenera con
//   python scripts/gen_catalogo_inmuebles.py
// (la plantilla de helpers vive en scripts/inmuebles-catalogo.plantilla.js).
//
// Lo usan: propiedades.html, propiedades-ficha.js, bolsa.html, buscador.html,
// ficha-manual.html, sitio-engine.js.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var CAT = __DATA__;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var TIPO = {}, TIPO_GRUPO = {}, TIPO_FAM = {}, OP = {}, CAR = {}, CAR_GRUPO = {};
  CAT.tipos.forEach(function (g) { g.items.forEach(function (t) { TIPO[t.key] = t.label; TIPO_GRUPO[t.key] = g.grupo; TIPO_FAM[t.key] = t.familia; }); });
  CAT.operaciones.forEach(function (o) { OP[o.key] = o; });
  CAT.caracteristicas.forEach(function (g) { g.items.forEach(function (c) { CAR[c.key] = c.label; CAR_GRUPO[c.key] = g.grupo; }); });
  function mapa(lista) { var m = {}; lista.forEach(function (x) { m[x.key] = x.label; }); return m; }
  var PERIODO = mapa(CAT.periodos), UNIDAD = mapa(CAT.unidades);
  var CONDICION = mapa(CAT.condiciones), DISPOSICION = mapa(CAT.disposiciones), ORIENTACION = mapa(CAT.orientaciones);

  // Tipo detallado de un inmueble: subtipo (nuevo) o tipo (viejo).
  function tipoDe(p) { return p ? (p.subtipo || p.tipo || '') : ''; }
  function tipoLabel(k) { return TIPO[k] || (k ? String(k).charAt(0).toUpperCase() + String(k).slice(1) : ''); }
  function opLabel(k) { return OP[k] ? OP[k].label : (k || ''); }

  // <option>s agrupados por <optgroup>. opts.vacio = texto de la opción vacía.
  function tiposOptions(sel, opts) {
    opts = opts || {};
    var h = opts.vacio != null ? '<option value="">' + esc(opts.vacio) + '</option>' : '';
    CAT.tipos.forEach(function (g) {
      h += '<optgroup label="' + esc(g.grupo) + '">';
      g.items.forEach(function (t) {
        h += '<option value="' + t.key + '"' + (t.key === sel ? ' selected' : '') + '>' + esc(t.label) + '</option>';
      });
      h += '</optgroup>';
    });
    return h;
  }
  function listaOptions(lista, sel, vacio) {
    var h = vacio != null ? '<option value="">' + esc(vacio) + '</option>' : '';
    lista.forEach(function (x) { h += '<option value="' + x.key + '"' + (x.key === sel ? ' selected' : '') + '>' + esc(x.label) + '</option>'; });
    return h;
  }

  // Operaciones de un inmueble, normalizadas. Si el inmueble es viejo (sin
  // columna operaciones) se arma una a partir de operacion/precio/moneda.
  function operaciones(p) {
    if (!p) return [];
    var ops = Array.isArray(p.operaciones) ? p.operaciones.filter(function (o) { return o && o.tipo; }) : [];
    if (ops.length) return ops;
    if (!p.operacion) return [];
    return [{ tipo: p.operacion, precio: p.precio, moneda: p.moneda || 'MXN', unidad: p.precio_unidad || 'total' }];
  }
  function tieneOperacion(p, k) {
    return operaciones(p).some(function (o) { return o.tipo === k; });
  }
  function fmtMonto(n, moneda) {
    var v = Number(n);
    if (!isFinite(v) || v <= 0) return 'Precio a consultar';
    return '$' + v.toLocaleString('es-MX', { maximumFractionDigits: 0 }) + ' ' + (moneda || 'MXN');
  }
  function precioTexto(o) {
    if (!o) return '';
    var t = fmtMonto(o.precio, o.moneda);
    if (o.unidad && o.unidad !== 'total' && UNIDAD[o.unidad]) t += ' ' + UNIDAD[o.unidad];
    if (o.tipo === 'renta_temporal' && o.periodo && PERIODO[o.periodo]) t += ' ' + PERIODO[o.periodo];
    else if (o.tipo === 'renta') t += ' / mes';
    return t;
  }
  function caractLabel(k) { return CAR[k] || k; }
  function caractPorGrupo(keys) {
    var set = {};
    (keys || []).forEach(function (k) { set[k] = true; });
    var out = [];
    CAT.caracteristicas.forEach(function (g) {
      var items = g.items.filter(function (c) { return set[c.key]; }).map(function (c) { return c.label; });
      if (items.length) out.push({ grupo: g.grupo, items: items });
    });
    return out;
  }
  // Casillas agrupadas para formularios/filtros. name = atributo name.
  function caractCheckboxes(name, seleccion, opts) {
    opts = opts || {};
    var set = {};
    (seleccion || []).forEach(function (k) { set[k] = true; });
    var grupos = opts.soloGrupo ? CAT.caracteristicas.filter(function (g) { return g.grupo === opts.soloGrupo; }) : CAT.caracteristicas;
    return grupos.map(function (g) {
      return '<fieldset class="bk-car-grupo"><legend>' + esc(g.grupo) + '</legend><div class="bk-car-items">' +
        g.items.map(function (c) {
          return '<label class="bk-car-item"><input type="checkbox" name="' + esc(name) + '" value="' + c.key + '"' +
            (set[c.key] ? ' checked' : '') + '/><span>' + esc(c.label) + '</span></label>';
        }).join('') + '</div></fieldset>';
    }).join('');
  }

  // ── Multimedia ──
  // ID de YouTube de cualquier forma de liga (watch, youtu.be, shorts, embed, live).
  function ytId(url) {
    var m = String(url || '').match(/(?:youtu\.be\/|youtube(?:-nocookie)?\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/|live\/|v\/))([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
  }
  function esHttps(url) { return /^https:\/\/[^\s"'<>]+$/i.test(String(url || '').trim()); }
  function iframe(src, titulo) {
    return '<div class="bk-embed"><iframe src="' + esc(src) + '" title="' + esc(titulo) + '" loading="lazy" ' +
      'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; xr-spatial-tracking; fullscreen" ' +
      'allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe></div>';
  }
  function videoEmbed(url) {
    var id = ytId(url);
    return id ? iframe('https://www.youtube-nocookie.com/embed/' + id, 'Video del inmueble') : '';
  }
  function tourEmbed(url) {
    url = String(url || '').trim();
    if (!esHttps(url)) return '';
    // Matterport: la liga "show" se embebe tal cual; Kuula: /share/ → /share/ (embed acepta ambas).
    return iframe(url, 'Tour virtual');
  }
  // Limpia una lista de ligas (texto con saltos de línea o arreglo).
  function ligas(v, soloYoutube) {
    var arr = Array.isArray(v) ? v : String(v || '').split(/[\n,]+/);
    var out = [];
    arr.forEach(function (x) {
      x = String(x || '').trim();
      if (!x) return;
      if (soloYoutube) { var id = ytId(x); if (id) x = 'https://www.youtube.com/watch?v=' + id; else return; }
      else if (!esHttps(x)) return;
      if (out.indexOf(x) === -1) out.push(x);
    });
    return out;
  }
  function multimediaHtml(p, opts) {
    opts = opts || {};
    var h = '';
    var vids = (p.videos || []).map(videoEmbed).filter(Boolean);
    var tours = (p.tours || []).map(tourEmbed).filter(Boolean);
    var docs = (p.documentos || []).filter(function (d) { return d && esHttps(d.url); });
    if (vids.length) h += '<div class="bk-mm"><h4>' + (vids.length > 1 ? 'Videos' : 'Video') + '</h4>' + vids.join('') + '</div>';
    if (tours.length) h += '<div class="bk-mm"><h4>Tour virtual</h4>' + tours.join('') + '</div>';
    if (docs.length) h += '<div class="bk-mm"><h4>Documentos</h4><ul class="bk-docs">' + docs.map(function (d) {
      return '<li><a href="' + esc(d.url) + '" target="_blank" rel="noopener" download>' + esc(d.nombre || 'Documento') + '</a>' +
        (d.tamano ? ' <span>' + Math.max(1, Math.round(d.tamano / 1024)) + ' KB</span>' : '') + '</li>';
    }).join('') + '</ul></div>';
    return h;
  }

  window.BK_CAT = CAT;
  window.bkCat = {
    data: CAT,
    esc: esc,
    tipoLabel: tipoLabel,
    tipoDe: tipoDe,
    tipoFamilia: function (k) { return TIPO_FAM[k] || k || ''; },
    tipoGrupo: function (k) { return TIPO_GRUPO[k] || ''; },
    tiposOptions: tiposOptions,
    listaOptions: listaOptions,
    opLabel: opLabel,
    opLegacy: function (k) { return OP[k] ? OP[k].legacy : k; },
    operaciones: operaciones,
    tieneOperacion: tieneOperacion,
    precioTexto: precioTexto,
    fmtMonto: fmtMonto,
    periodoLabel: function (k) { return PERIODO[k] || ''; },
    unidadLabel: function (k) { return UNIDAD[k] || ''; },
    condicionLabel: function (k) { return CONDICION[k] || k || ''; },
    disposicionLabel: function (k) { return DISPOSICION[k] || k || ''; },
    orientacionLabel: function (k) { return ORIENTACION[k] || k || ''; },
    caractLabel: caractLabel,
    caractGrupo: function (k) { return CAR_GRUPO[k] || ''; },
    caractPorGrupo: caractPorGrupo,
    caractCheckboxes: caractCheckboxes,
    ytId: ytId,
    esHttps: esHttps,
    videoEmbed: videoEmbed,
    tourEmbed: tourEmbed,
    ligas: ligas,
    multimediaHtml: multimediaHtml
  };
  // Estilos mínimos de multimedia (la usan páginas con hojas distintas).
  if (typeof document !== 'undefined' && !document.getElementById('bk-mm-css')) {
    var st = document.createElement('style'); st.id = 'bk-mm-css';
    st.textContent = '.bk-embed{position:relative;width:100%;aspect-ratio:16/9;border-radius:var(--r,12px);overflow:hidden;background:var(--paper-2,#eee);margin:0 0 10px}' +
      '.bk-embed iframe{position:absolute;inset:0;width:100%;height:100%;border:0}' +
      '.bk-mm{margin:14px 0}.bk-mm h4{margin:0 0 8px;font-size:var(--fs-sm,14px);font-weight:600}' +
      '.bk-docs{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:6px}' +
      '.bk-docs a{font-weight:600;color:inherit;text-decoration:underline}.bk-docs span{color:var(--mute,#777);font-size:var(--fs-xs,12px)}';
    (document.head || document.documentElement).appendChild(st);
  }
})();
