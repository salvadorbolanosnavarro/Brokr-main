// alertas.js · Página "Alertas de búsqueda": todos los requerimientos
// activos del equipo (routers/alertas.py), filtrables por agente; se pueden
// pausar, editar (abre la ficha del contacto) o eliminar.
(function () {
  'use strict';
  var esc = window.bkEsc, api = window.bkApi, toast = window.bkToast;
  var miembros = [], datos = [], cargaActual = 0;
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
    g('al-lista').setAttribute('aria-busy', 'false');
    g('al-lista').dataset.state = lista.length ? 'data' : 'empty';
    if (!lista.length) { window.bkRenderState('al-lista', 'empty', { title: 'No hay alertas', detail: 'Guarda el requerimiento de un contacto desde su ficha o prueba otro filtro.' }); return; }
    g('al-lista').innerHTML = lista.map(function (r) {
      return '<div class="crm-fila"><span class="crm-nombre">' + esc(r.contacto_nombre) +
        (r.nuevas ? ' <span class="crm-badge">' + r.nuevas + ' nuevas</span>' : '') +
        '<small>' + esc(resumen(r)) + '</small><small>' + esc(nombre(r.agente_id) ? 'Agente: ' + nombre(r.agente_id) : '') + (r.activo ? '' : ' · Pausada') + '</small></span>' +
        '<span class="crm-acciones"><a class="bk-btn bk-btn--ghost bk-btn--sm" href="contactos.html?id=' + encodeURIComponent(r.contacto_id) + '&tab=requerimiento">Editar</a>' +
        '<button class="bk-btn bk-btn--ghost bk-btn--sm" data-pausa="' + esc(r.id) + '" data-activo="' + (r.activo ? '0' : '1') + '">' + (r.activo ? 'Pausar' : 'Reanudar') + '</button>' +
        '<button class="bk-btn bk-btn--danger bk-btn--sm" data-del="' + esc(r.id) + '">Eliminar</button></span></div>';
    }).join('');
  }
  async function cargar() {
    var carga = ++cargaActual;
    window.bkRenderState('al-lista', 'loading', { title: 'Cargando alertas…' });
    var a = g('al-agente').value;
    try { var respuesta = (await api('/alertas/requerimientos' + (a ? '?agente=' + encodeURIComponent(a) : ''))); if (carga !== cargaActual) return; datos = respuesta.requerimientos || []; }
    catch (e) { if (carga !== cargaActual) return; window.bkRenderState('al-lista', 'error', { title: 'No se pudieron cargar las alertas', detail: e.message, onRetry: cargar }); return; }
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
