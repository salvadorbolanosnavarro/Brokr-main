// ─────────────────────────────────────────────────────────────────────────
// estadisticas-plus.js · Pestañas nuevas de Estadísticas (vive fuera de
// estadisticas.html, que está en su techo de tamaño):
//   · Buzón: tiempo de primera respuesta por agente y por canal.
// Otras fases suman pestañas con window.esRegistrarPestana({id,titulo,render}).
// Usa los globales de estadisticas.html: tab, periodo, render, kpi, sec, esc.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var PESTANAS = {};
  function desdePeriodo() {
    var d = new Date();
    if (typeof periodo === 'undefined' || periodo === 'todo') return '';
    if (periodo === 'semana') d.setDate(d.getDate() - 7);
    else if (periodo === 'mes') d.setMonth(d.getMonth() - 1);
    else if (periodo === 'trimestre') d.setMonth(d.getMonth() - 3);
    return d.toISOString().slice(0, 10);
  }
  window.esDesdePeriodo = desdePeriodo;
  function dur(seg) {
    if (seg == null) return '—';
    if (seg < 60) return seg + ' s'; if (seg < 3600) return Math.round(seg / 60) + ' min';
    if (seg < 86400) return (seg / 3600).toFixed(1).replace('.0', '') + ' h'; return (seg / 86400).toFixed(1).replace('.0', '') + ' d';
  }
  window.esRegistrarPestana = function (p) {
    PESTANAS[p.id] = p;
    var tabs = document.getElementById('es-tabs');
    if (tabs && !tabs.querySelector('[data-tab="' + p.id + '"]')) {
      tabs.insertAdjacentHTML('beforeend', '<button class="ftab" data-tab="' + p.id + '" onclick="setTab(\'' + p.id + '\')">' + p.titulo + '</button>');
    }
  };
  if (typeof render === 'function') {
    var _render = render;
    render = function () {
      if (typeof tab !== 'undefined' && PESTANAS[tab]) {
        var body = document.getElementById('es-body');
        body.innerHTML = '<div class="es-loading">Cargando…</div>';
        Promise.resolve(PESTANAS[tab].render(body)).catch(function (e) { body.innerHTML = '<div class="es-loading">' + window.bkEsc(e.message) + '</div>'; });
        return;
      }
      return _render.apply(this, arguments);
    };
  }

  var CANALES = { whatsapp: 'WhatsApp', sitio: 'Sitio web', bolsa: 'Bolsa Broquer', zapier: 'Zapier', easybroker: 'EasyBroker',
    telefono: 'Llamada', manual: 'Captura manual', meta: 'Meta Lead Ads', portal: 'Portal inmobiliario', correo: 'Correo' };
  async function renderBuzon(body) {
    var esc = window.bkEsc;
    var desde = desdePeriodo();
    var datos = await window.bkApi('/buzon/estadisticas' + (desde ? '?desde=' + desde : ''));
    var miembros = [];
    try { miembros = (await window.bkApi('/org/miembros')).miembros || []; } catch (e) {}
    var nombre = function (uid) { if (uid === 'sin_asignar') return 'Sin asignar'; var m = miembros.find(function (x) { return x.user_id === uid; }); return m ? (m.nombre || m.email) : 'Agente'; };
    var t = datos.total || {};
    var tabla = function (titulo, obj, etiqueta) {
      var filas = Object.keys(obj || {}).map(function (k) { return [k, obj[k]]; }).sort(function (a, b) { return b[1].leads - a[1].leads; });
      return sec(titulo, 'mediana de primera respuesta', '<div class="es-card es-tablewrap"><table class="es-table"><thead><tr><th>' + etiqueta + '</th><th class="num">Leads</th><th class="num">Respondidos</th><th class="num">Mediana</th><th class="num">Promedio</th></tr></thead><tbody>' +
        (filas.length ? filas.map(function (f) {
          return '<tr><td class="t">' + esc(etiqueta === 'Agente' ? nombre(f[0]) : (CANALES[f[0]] || f[0])) + '</td><td class="num">' + f[1].leads + '</td><td class="num">' + f[1].respondidos +
            '</td><td class="num">' + dur(f[1].mediana_seg) + '</td><td class="num">' + dur(f[1].promedio_seg) + '</td></tr>';
        }).join('') : '<tr><td colspan="5">Sin leads en este periodo.</td></tr>') + '</tbody></table></div>');
    };
    body.innerHTML = '<div class="es-kpis">' +
      kpi(t.leads || 0, 'Leads en el Buzón') + kpi(t.respondidos || 0, 'Respondidos') +
      kpi(dur(t.mediana_seg), 'Primera respuesta (mediana)') + kpi(dur(t.promedio_seg), 'Primera respuesta (promedio)') +
      '</div>' + tabla('Por agente', datos.por_agente, 'Agente') + tabla('Por canal', datos.por_canal, 'Canal');
  }
  window.esRegistrarPestana({ id: 'buzon', titulo: 'Buzón', render: renderBuzon });

  // ── Operaciones cerradas (routers/cierres.py) ──
  var agenteCierres = '';
  function hoyMenos() { return desdePeriodo(); }
  async function descargarCsv() {
    var tok = await window.brokrSb.ensureToken();
    var qs = new URLSearchParams(); if (hoyMenos()) qs.set('desde', hoyMenos()); if (agenteCierres) qs.set('agente', agenteCierres);
    var r = await fetch((window.API_BASE || 'https://api.broquer.app') + '/cierres/reporte.csv?' + qs, { headers: { Authorization: 'Bearer ' + tok } });
    if (!r.ok) { var d = await r.json().catch(function () { return {}; }); window.bkToast(d.detail || 'No se pudo exportar'); return; }
    var a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = 'operaciones-cerradas.csv';
    document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  function parseCsv(texto) {
    var filas = [], fila = [], campo = '', q = false;
    texto = texto.replace(/^\ufeff/, '');
    for (var i = 0; i < texto.length; i++) {
      var ch = texto[i];
      if (q) { if (ch === '"' && texto[i + 1] === '"') { campo += '"'; i++; } else if (ch === '"') q = false; else campo += ch; }
      else if (ch === '"') q = true;
      else if (ch === ',') { fila.push(campo); campo = ''; }
      else if (ch === '\n' || ch === '\r') { if (ch === '\r' && texto[i + 1] === '\n') i++; fila.push(campo); campo = ''; if (fila.some(function (x) { return x !== ''; })) filas.push(fila); fila = []; }
      else campo += ch;
    }
    fila.push(campo); if (fila.some(function (x) { return x !== ''; })) filas.push(fila);
    var cab = (filas.shift() || []).map(function (h) { return h.trim().toLowerCase(); });
    return filas.map(function (f) { var o = {}; cab.forEach(function (h, j) { o[h] = (f[j] || '').trim(); }); return o; });
  }
  async function renderCierres(body) {
    var esc = window.bkEsc;
    var miembros = [];
    try { miembros = ((await window.bkApi('/org/miembros')).miembros || []).filter(function (m) { return m.activo !== false; }); } catch (e) {}
    var qs = new URLSearchParams(); if (hoyMenos()) qs.set('desde', hoyMenos()); if (agenteCierres) qs.set('agente', agenteCierres);
    var d;
    try { d = await window.bkApi('/cierres/reporte?' + qs); }
    catch (e) { body.innerHTML = '<div class="es-loading">' + esc(e.message) + '</div>'; return; }
    var filas = d.filas || [], cols = d.columnas || [];
    var m = function (n) { return n == null ? '—' : '$' + Math.round(n).toLocaleString('es-MX'); };
    var sum = function (k) { return filas.reduce(function (a, f) { return a + (Number(f[k]) || 0); }, 0); };
    var dias = filas.filter(function (f) { return f.dias_publicada != null; });
    var pct = filas.filter(function (f) { return f.pct_precio != null; });
    var MONEY = { precio_publicacion: 1, precio_cierre: 1, comision_total: 1, comision_inmobiliaria: 1, opcionador_comision: 1, asesor_comision: 1 };
    body.innerHTML =
      '<div class="es-kpis">' + kpi(filas.length, 'Operaciones cerradas') + kpi(m(sum('comision_total')), 'Comisión total') +
        kpi(dias.length ? Math.round(dias.reduce(function (a, f) { return a + f.dias_publicada; }, 0) / dias.length) : '—', 'Días publicada (promedio)') +
        kpi(pct.length ? (pct.reduce(function (a, f) { return a + f.pct_precio; }, 0) / pct.length).toFixed(1) + '%' : '—', 'Del precio de publicación') + '</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:12px 0">' +
        (miembros.length > 1 ? '<select class="bk-select" id="es-ci-agente" style="width:auto"><option value="">Todo el equipo</option>' +
          miembros.map(function (x) { return '<option value="' + esc(x.user_id) + '"' + (x.user_id === agenteCierres ? ' selected' : '') + '>' + esc(x.nombre || x.email) + '</option>'; }).join('') + '</select>' : '') +
        '<button class="bk-btn bk-btn--ghost bk-btn--sm" id="es-ci-csv">Exportar CSV</button>' +
        '<a class="bk-btn bk-btn--quiet bk-btn--sm" href="' + (window.API_BASE || 'https://api.broquer.app') + '/cierres/plantilla.csv">Plantilla para cargar cierres</a>' +
        '<label class="bk-btn bk-btn--quiet bk-btn--sm" style="cursor:pointer">Cargar cierres (CSV)<input type="file" accept=".csv,text/csv" id="es-ci-file" hidden/></label>' +
      '</div>' +
      sec('Operaciones cerradas', 'el periodo de arriba', '<div class="es-card es-tablewrap"><table class="es-table"><thead><tr>' +
        cols.map(function (c) { return '<th' + (MONEY[c[0]] || c[0] === 'dias_publicada' || c[0] === 'pct_precio' ? ' class="num"' : '') + '>' + esc(c[1]) + '</th>'; }).join('') + '</tr></thead><tbody>' +
        (filas.length ? filas.map(function (f) {
          return '<tr onclick="location.href=\'propiedades.html?id=' + encodeURIComponent(f.propiedad_id) + '\'">' + cols.map(function (c) {
            var v = f[c[0]];
            if (MONEY[c[0]]) return '<td class="num">' + m(v) + '</td>';
            if (c[0] === 'pct_precio') return '<td class="num">' + (v == null ? '—' : v + '%') + '</td>';
            if (c[0] === 'dias_publicada') return '<td class="num">' + (v == null ? '—' : v) + '</td>';
            return '<td' + (c[0] === 'inmueble' ? ' class="t"' : '') + '>' + esc(v == null ? '' : v) + '</td>';
          }).join('') + '</tr>';
        }).join('') : '<tr><td colspan="' + cols.length + '">Sin cierres en este periodo.</td></tr>') + '</tbody></table></div>');
    var sa = document.getElementById('es-ci-agente'); if (sa) sa.onchange = function () { agenteCierres = sa.value; render(); };
    document.getElementById('es-ci-csv').onclick = descargarCsv;
    document.getElementById('es-ci-file').onchange = async function () {
      var f = this.files[0]; if (!f) return;
      try {
        var r = await window.bkApi('/cierres/importar', { method: 'POST', json: { filas: parseCsv(await f.text()) } });
        alert(r.importados + ' cierres importados.' + (r.errores.length ? '\n\nCon error:\n' + r.errores.slice(0, 15).map(function (e) { return 'Fila ' + e.fila + ': ' + e.motivo; }).join('\n') : ''));
        render();
      } catch (e) { alert(e.message); }
    };
  }
  window.esRegistrarPestana({ id: 'cierres', titulo: 'Operaciones cerradas', render: renderCierres });
})();
