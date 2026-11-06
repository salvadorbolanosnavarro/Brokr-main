/* ══════════════════════════════════════════════════════════════════
   Consola de dueño · Seguridad de archivos.

   Agrega al Panorama un botón para descargar el reporte de archivos
   riesgosos ya guardados (GET /admin/archivos/reporte): archivos con tipo
   que el navegador ejecutaría (HTML, SVG, scripts) y archivos de clientes
   en buckets públicos. El backend solo lee nombres y metadatos: no abre,
   copia ni borra nada.
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  var wrap = document.querySelector('#v-panorama .ac-wrap');
  if (!wrap || typeof api !== 'function' || document.getElementById('arch-reporte-btn')) return;

  var sec = document.createElement('div');
  sec.className = 'ac-sec';
  sec.innerHTML =
    '<div class="ac-sec__h"><h2>Seguridad de archivos</h2><span>No borra ningún archivo</span></div>' +
    '<div class="ac-card">' +
    '<p class="ac-sub">Archivos ya guardados con tipo riesgoso (HTML, SVG, scripts) o archivos de clientes en ' +
    'buckets públicos. El reporte puede traer nombres de archivo de clientes: guárdalo en privado.</p>' +
    '<button type="button" class="ac-btn" id="arch-reporte-btn">Descargar reporte de archivos</button> ' +
    '<span class="ac-sub" id="arch-reporte-msg" role="status"></span>' +
    '<p class="ac-sub">Inmuebles con fotos ligadas a chats de WhatsApp o adjuntos: cópialas al inventario ' +
    'antes de volver privados esos archivos (no borra nada).</p>' +
    '<button type="button" class="ac-btn" id="arch-copiar-btn">Copiar fotos de inmuebles al inventario</button> ' +
    '<span class="ac-sub" id="arch-copiar-msg" role="status"></span></div>';
  wrap.appendChild(sec);

  var copiar = document.getElementById('arch-copiar-btn');
  var copiarMsg = document.getElementById('arch-copiar-msg');
  copiar.addEventListener('click', async function () {
    copiar.disabled = true;
    copiarMsg.textContent = 'Copiando fotos…';
    try {
      var r = await api('/admin/archivos/copiar-fotos', { method: 'POST' });
      var d = await r.json().catch(function () { return {}; });
      if (!r.ok) throw new Error(d.detail || ('Error ' + r.status));
      copiarMsg.textContent = 'Listo: ' + d.fotos_copiadas + ' foto(s) copiadas en ' + d.inmuebles + ' inmueble(s)' +
        (d.fotos_no_copiadas ? '; ' + d.fotos_no_copiadas + ' no se pudieron copiar.' : '.');
    } catch (err) {
      copiarMsg.textContent = (err && err.message) || 'No se pudieron copiar las fotos.';
    } finally {
      copiar.disabled = false;
    }
  });

  var btn = document.getElementById('arch-reporte-btn');
  var msg = document.getElementById('arch-reporte-msg');
  btn.addEventListener('click', async function () {
    btn.disabled = true;
    msg.textContent = 'Revisando archivos… puede tardar unos minutos.';
    try {
      var r = await api('/admin/archivos/reporte');
      if (!r.ok) {
        var m = 'Error ' + r.status;
        try { var e = await r.json(); if (e.detail) m = e.detail; } catch (_) {}
        throw new Error(m);
      }
      var blob = await r.blob();
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'reporte-archivos.csv';
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
      msg.textContent = 'Listo. Ábrelo con Excel o Google Sheets.';
    } catch (err) {
      msg.textContent = (err && err.message) || 'No se pudo generar el reporte.';
    } finally {
      btn.disabled = false;
    }
  });
})();
