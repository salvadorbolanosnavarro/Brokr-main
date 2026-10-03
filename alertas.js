// alertas.js · Página "Alertas de búsqueda": todos los requerimientos
// activos del equipo (routers/alertas.py), filtrables por agente; se pueden
// pausar, editar (abre la ficha del contacto) o eliminar.
(function () {
  'use strict';
  var esc = window.bkEsc, api = window.bkApi, toast = window.bkToast;
  var miembros = [], datos = [];
  function g(id) { return document.getElementById(id); }
  function nombre(uid) { var m = miembros.find(function (x) { return x.user_id === uid; }); return m ? (m.nombre || m.email) : ''; }
  function resumen(r) {
    var C = window.bkCat, partes = [];
    var ops = (r.operaciones && r.operaciones.length ? r.operaciones : [r.operacion]).filter(Boolean);
    if (ops.length) partes.push(ops.map(function (o) { return C ? C.opLabel(o) : o; }).join('/'));
    var tipos = (r.tipos && r.tipos.length ? r.tipos : [r.tipo_inmueble]).filter(Boolean);
    if (tipos.length) partes.push(tipos.map(function (t) { return C ? C.tipoLabel(t) : t; }).join(', '));
    var zonas = (r.zonas && r.zonas.length ? r.zonas : [r.colonia, r.ciudad]).filter(Boolean);
    if (zonas.length) partes.push(zonas.join(', '));
    if (r.precio_min || r.precio_max) partes.push((r.precio_min ? '$' + Number(r.precio_min).toLocaleString('es-MX') : '') + '–' + (r.precio_max ? '$' + Number(r.precio_max).toLocaleString('es-MX') : '') + ' ' + (r.moneda || 'MXN'));
    if (r.recamaras_min) partes.push(r.recamaras_min + '+ rec');
    return partes.join(' · ');
  }
  function pintar() {
    var est = g('al-estado').value;
    var lista = datos.filter(function (r) { return !est || (est === 'activos' ? r.activo : !r.activo); });
    g('al-lista').innerHTML = lista.length ? lista.map(function (r) {
      return '<div class="crm-fila"><span class="crm-nombre">' + esc(r.contacto_nombre) +
        (r.nuevas ? ' <span class="crm-badge">' + r.nuevas + ' nuevas</span>' : '') +
        '<small>' + esc(resumen(r)) + '</small><small>' + esc(nombre(r.agente_id) ? 'Agente: ' + nombre(r.agente_id) : '') + (r.activo ? '' : ' · Pausada') + '</small></span>' +
        '<span class="crm-acciones"><a class="bk-btn bk-btn--ghost bk-btn--sm" href="contactos.html?id=' + encodeURIComponent(r.contacto_id) + '&tab=requerimiento">Editar</a>' +
        '<button class="bk-btn bk-btn--ghost bk-btn--sm" data-pausa="' + esc(r.id) + '" data-activo="' + (r.activo ? '0' : '1') + '">' + (r.activo ? 'Pausar' : 'Reanudar') + '</button>' +
        '<button class="bk-btn bk-btn--danger bk-btn--sm" data-del="' + esc(r.id) + '">Eliminar</button></span></div>';
    }).join('') : '<div class="bk-empty"><div class="bk-empty__title">No hay alertas</div><div class="bk-empty__text">Guarda el requerimiento de un contacto (pestaña Requerimiento de su ficha) y aparecerá aquí.</div></div>';
  }
  async function cargar() {
    var a = g('al-agente').value;
    try { datos = (await api('/alertas/requerimientos' + (a ? '?agente=' + encodeURIComponent(a) : ''))).requerimientos || []; }
    catch (e) { g('al-lista').innerHTML = '<p>' + esc(e.message) + '</p>'; return; }
    pintar();
  }
  g('al-lista').addEventListener('click', async function (e) {
    var p = e.target.closest('[data-pausa]'), d = e.target.closest('[data-del]');
    try {
      if (p) { await api('/alertas/requerimientos/' + p.dataset.pausa, { method: 'PATCH', json: { activo: p.dataset.activo === '1' } }); toast(p.dataset.activo === '1' ? 'Alerta reanudada' : 'Alerta pausada'); cargar(); }
      if (d && confirm('¿Eliminar este requerimiento y sus alertas?')) { await api('/alertas/requerimientos/' + d.dataset.del, { method: 'DELETE' }); toast('Eliminado'); cargar(); }
    } catch (err) { toast(err.message); }
  });
  g('al-agente').onchange = cargar;
  g('al-estado').onchange = pintar;
  (async function () {
    try { miembros = ((await api('/org/miembros')).miembros || []).filter(function (m) { return m.activo !== false; }); } catch (e) {}
    if (miembros.length > 1) g('al-agente').innerHTML += miembros.map(function (m) { return '<option value="' + esc(m.user_id) + '">' + esc(m.nombre || m.email) + '</option>'; }).join('');
    else g('al-agente').hidden = true;
    cargar();
  })();
})();
