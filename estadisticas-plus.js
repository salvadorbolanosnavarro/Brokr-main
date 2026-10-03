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
})();
