// ─────────────────────────────────────────────────────────────────────────
// propiedades-cierre.js · Modal de cierre (reemplaza a "Registrar comisión").
// Se abre al cambiar el estatus de un inmueble a Reservada, Vendida o
// Rentada, sólo para quien tiene el permiso "Ver comisiones" (los demás
// cambian el estatus como siempre, sin montos). Guarda en /cierres
// (routers/cierres.py): crea los ingresos por cobrar en Finanzas y, en
// ventas, corre la revisión PLD de Cumplimiento.
// Lo carga propiedades-plus.js.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var esc = window.bkEsc, api = window.bkApi;
  var CONTACTOS = null;
  function g(id) { return document.getElementById(id); }
  function puedeVerComisiones() {
    var per = window.pPermisos || {};
    return (typeof pEsAdminOrg !== 'undefined' && pEsAdminOrg) || per.ver_comisiones === true || !(typeof pEsEmpresa !== 'undefined' && pEsEmpresa);
  }
  async function contactos() {
    if (CONTACTOS) return CONTACTOS;
    try { CONTACTOS = await window.bkRest('contactos?select=id,nombre,telefono&order=nombre.asc&limit=5000'); } catch (e) { CONTACTOS = []; }
    return CONTACTOS;
  }
  function campo(lbl, ctrl) { return '<div class="pf-field"><label>' + lbl + '</label>' + ctrl + '</div>'; }
  function money(id, v) { return '<input type="number" min="0" step="any" inputmode="decimal" id="' + id + '" value="' + (v == null ? '' : v) + '"/>'; }
  function moneda(id, v) { return '<select id="' + id + '"><option' + (v === 'USD' ? '' : ' selected') + '>MXN</option><option' + (v === 'USD' ? ' selected' : '') + '>USD</option></select>'; }
  function fecha(id, v) { return '<input type="date" id="' + id + '" value="' + (v || '') + '"/>'; }
  function parte(rol, titulo, c) {
    var miembros = (typeof pMiembros !== 'undefined' && pMiembros) || [];
    var interno = !!c[rol + '_user_id'] || (!c[rol + '_contacto_id'] && !c[rol + '_nombre']);
    return '<div class="pf-section">' + titulo + '</div><div class="pf-row">' +
      campo('Es', '<select id="ci-' + rol + '-tipo"><option value="equipo"' + (interno ? ' selected' : '') + '>Alguien del equipo</option><option value="externo"' + (interno ? '' : ' selected') + '>Contacto o agencia externa</option></select>') +
      '<div class="pf-field" id="ci-' + rol + '-eq"' + (interno ? '' : ' hidden') + '><label>Usuario</label><select id="ci-' + rol + '-user"><option value="">Nadie</option>' +
        miembros.map(function (m) { return '<option value="' + esc(m.user_id) + '"' + (m.user_id === c[rol + '_user_id'] ? ' selected' : '') + '>' + esc(m.nombre || m.email) + '</option>'; }).join('') + '</select></div>' +
      '<div class="pf-field" id="ci-' + rol + '-ex"' + (interno ? ' hidden' : '') + '><label>Contacto o agencia</label><input id="ci-' + rol + '-nombre" list="ci-contactos" value="' + esc(c[rol + '_nombre'] || '') + '" placeholder="Nombre"/></div>' +
      campo('Su comisión', money('ci-' + rol + '-com', c[rol + '_comision'])) + '</div>';
  }

  window.pxAbrirCierre = async function (propiedadId, estatus) {
    var d;
    try { d = await api('/cierres/propiedad/' + encodeURIComponent(propiedadId)); }
    catch (e) { alert(e.message); return false; }
    var p = d.propiedad || {}, c = d.cierre || {};
    var renta = estatus === 'rentada';
    var lista = await contactos();
    var comprador = lista.find(function (x) { return x.id === c.comprador_contacto_id; });
    var ov = g('ci-modal');
    if (!ov) { ov = document.createElement('div'); ov.id = 'ci-modal'; ov.className = 'prop-modal-overlay'; document.body.appendChild(ov); }
    var titulo = { reservada: 'Registrar reserva', vendida: 'Registrar cierre de venta', rentada: 'Registrar cierre de renta' }[estatus];
    var esCierre = estatus !== 'reservada';
    ov.innerHTML = '<div class="prop-modal-box" onclick="event.stopPropagation()"><div class="prop-modal-hdr"><h3>' + titulo + '</h3>' +
      '<button class="prop-modal-close" aria-label="Cerrar" id="ci-x"><svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 18L18 6M6 6l12 12"/></svg></button></div>' +
      '<div class="prop-modal-body"><form onsubmit="return false"><datalist id="ci-contactos">' + lista.map(function (x) { return '<option value="' + esc(x.nombre) + '"></option>'; }).join('') + '</datalist>' +
      '<p style="color:var(--mute);font-size:var(--fs-sm);margin:0 0 12px">' + esc(p.titulo || '') + '</p>' +
      '<div class="pf-section">Reserva</div><div class="pf-row">' + campo('Fecha de apartado', fecha('ci-fres', c.fecha_reserva)) +
        campo('Monto de apartado', money('ci-mres', c.monto_reserva)) + campo('Moneda', moneda('ci-mondres', c.moneda_reserva)) + '</div>' +
      (esCierre ? '<div class="pf-section">Cierre</div><div class="pf-row">' + campo('Fecha de cierre', fecha('ci-fcie', c.fecha_cierre || new Date().toISOString().slice(0, 10))) +
        campo('Precio final', money('ci-precio', c.precio_cierre != null ? c.precio_cierre : p.precio)) + campo('Moneda', moneda('ci-moncie', c.moneda_cierre || p.moneda)) + '</div>' +
        '<div class="pf-row"><div class="pf-field full"><label>' + (renta ? 'Arrendatario' : 'Comprador') + ' (contacto)</label><input id="ci-comprador" list="ci-contactos" value="' + esc(comprador ? comprador.nombre : '') + '" placeholder="Busca un contacto"/></div></div>' : '') +
      '<div class="pf-section">Comisión</div><div class="pf-row">' +
        campo('Calcular como', '<select id="ci-ctipo"><option value="monto">Monto</option><option value="pct"' + (c.comision_tipo === 'pct' ? ' selected' : '') + '>% del precio</option>' +
          (renta ? '<option value="meses"' + (c.comision_tipo === 'meses' || (!c.comision_tipo) ? ' selected' : '') + '>Meses de renta</option>' : '') + '</select>') +
        campo('Valor', money('ci-cvalor', c.comision_valor != null ? c.comision_valor : (renta ? p.comision_renta_meses : p.comision_venta_pct))) +
        campo('Comisión total', '<input id="ci-ctotal" readonly/>') + '</div>' +
      '<div class="pf-row">' + campo('Comisión de la inmobiliaria', money('ci-cinmo', c.comision_inmobiliaria)) + '</div>' +
      parte('opcionador', 'Opcionador (representa al propietario)', c) +
      parte('asesor', 'Asesor (representa al ' + (renta ? 'arrendatario' : 'comprador') + ')', c) +
      '<div id="ci-aviso" class="px-nota" role="status" style="margin-bottom:8px"></div>' +
      '<div class="pf-row"><div class="pf-field full"><label>Notas</label><textarea id="ci-notas" rows="2">' + esc(c.notas || '') + '</textarea></div></div>' +
      '<div class="pf-actions"><button type="button" class="pf-cancel-btn" id="ci-cancelar">Cancelar</button><button type="button" class="pf-save-btn" id="ci-ok">Guardar</button></div>' +
      '</form></div></div>';
    if (!c.comision_tipo && !renta && p.comision_venta_pct) g('ci-ctipo').value = 'pct';
    ov.style.display = 'flex';

    function num(id) { var e = g(id); return e && e.value !== '' ? Number(e.value) : null; }
    function total() {
      var t = g('ci-ctipo').value, v = num('ci-cvalor'), precio = num('ci-precio') != null ? num('ci-precio') : Number(p.precio) || 0;
      if (v == null) return null;
      return t === 'pct' ? precio * v / 100 : (t === 'meses' ? precio * v : v);
    }
    function validar() {
      var tot = total();
      g('ci-ctotal').value = tot == null ? '' : '$' + Math.round(tot).toLocaleString('es-MX');
      var suma = (num('ci-cinmo') || 0) + (num('ci-opcionador-com') || 0) + (num('ci-asesor-com') || 0);
      var av = g('ci-aviso');
      if (tot != null && suma > 0 && Math.abs(suma - tot) > 1) {
        av.textContent = 'Ojo: las partes suman $' + Math.round(suma).toLocaleString('es-MX') + ' y la comisión total es $' + Math.round(tot).toLocaleString('es-MX') + '. Puedes guardar así.';
        av.style.color = 'var(--warn)';
      } else { av.textContent = ''; }
    }
    ov.querySelector('form').addEventListener('input', validar);
    ['opcionador', 'asesor'].forEach(function (rol) {
      g('ci-' + rol + '-tipo').onchange = function () { var eq = this.value === 'equipo'; g('ci-' + rol + '-eq').hidden = !eq; g('ci-' + rol + '-ex').hidden = eq; };
    });
    validar();
    return new Promise(function (resolve) {
      var cerrar = function (ok) { ov.style.display = 'none'; resolve(ok); };
      g('ci-x').onclick = g('ci-cancelar').onclick = function () { cerrar(false); };
      ov.onclick = function (e) { if (e.target === ov) cerrar(false); };
      g('ci-ok').onclick = async function () {
        var btn = this; btn.disabled = true;
        var nombreA = function (id) { var v = (g(id) || {}).value || ''; var m = lista.find(function (x) { return x.nombre === v; }); return { id: m ? m.id : null, nombre: v.trim() }; };
        var comp = esCierre ? nombreA('ci-comprador') : { id: null };
        var body = {
          propiedad_id: propiedadId, estatus: estatus,
          fecha_reserva: (g('ci-fres') || {}).value || null, monto_reserva: num('ci-mres'), moneda_reserva: g('ci-mondres').value,
          fecha_cierre: esCierre ? g('ci-fcie').value || null : null, precio_cierre: esCierre ? num('ci-precio') : null,
          moneda_cierre: esCierre ? g('ci-moncie').value : 'MXN', comprador_contacto_id: comp.id,
          comision_tipo: g('ci-ctipo').value, comision_valor: num('ci-cvalor'), moneda_comision: esCierre ? g('ci-moncie').value : 'MXN',
          comision_inmobiliaria: num('ci-cinmo'), notas: g('ci-notas').value,
        };
        ['opcionador', 'asesor'].forEach(function (rol) {
          var eq = g('ci-' + rol + '-tipo').value === 'equipo';
          var ext = nombreA('ci-' + rol + '-nombre');
          body[rol + '_user_id'] = eq ? (g('ci-' + rol + '-user').value || null) : null;
          body[rol + '_contacto_id'] = eq ? null : ext.id;
          body[rol + '_nombre'] = eq ? null : (ext.nombre || null);
          body[rol + '_comision'] = num('ci-' + rol + '-com');
        });
        try {
          var r = await api('/cierres', { method: 'POST', json: body });
          var msg = { reservada: 'Reserva registrada', vendida: 'Cierre de venta registrado', rentada: 'Cierre de renta registrado' }[estatus];
          if (r.movimientos && r.movimientos.length) msg += ' · ' + r.movimientos.length + ' comisión(es) por cobrar en Finanzas';
          mostrarToast(msg);
          if (r.pld && r.pld.genera_aviso) setTimeout(function () { alert('Esta venta puede generar aviso PLD. La operación quedó prellenada en Cumplimiento: revísala y completa el expediente.'); }, 300);
          cerrar(true);
        } catch (e) { btn.disabled = false; alert('No se pudo guardar: ' + e.message); }
      };
    });
  };

  // El cambio de estatus desde la ficha abre el modal de cierre.
  if (typeof pdCambiarEstatus === 'function') {
    var orig = pdCambiarEstatus;
    pdCambiarEstatus = async function (v) {
      if (['reservada', 'vendida', 'rentada'].indexOf(v) === -1 || !puedeVerComisiones()) return orig.apply(this, arguments);
      var pid = currentDetailId; if (!pid) return;
      var ok = await window.pxAbrirCierre(pid, v);
      if (ok) { await loadProps(); if (typeof openPropDetail === 'function') openPropDetail(pid); }
    };
  }
  // "Registrar comisión" (flujo viejo) ahora abre el cierre completo.
  if (typeof abrirComisionModal === 'function') {
    abrirComisionModal = function (p) { window.pxAbrirCierre(p.id, p.estatus === 'rentada' ? 'rentada' : 'vendida').then(function (ok) { if (ok) loadProps(); }); };
  }
})();
