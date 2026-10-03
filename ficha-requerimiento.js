// ─────────────────────────────────────────────────────────────────────────
// ficha-requerimiento.js · Pestaña "Requerimiento" de la ficha de contacto.
//
// Contactos es un solo módulo con dos vistas (Lista y Pipeline) y una sola
// ficha. La vista Pipeline (clientes.html) ya trae esta pestaña; en la vista
// Lista (contactos.html) este archivo la inyecta, con las mismas llamadas al
// Buscador de propiedades (/api/buscador/requerimiento/…).
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  function el(id) { return document.getElementById(id); }
  function esc(s) { return window.bkEsc ? window.bkEsc(s) : String(s == null ? '' : s); }
  function val(id) { var e = el(id); return e ? String(e.value || '').trim() : ''; }
  function put(id, v) { var e = el(id); if (e) e.value = v == null ? '' : v; }
  function toast(t) { (typeof showToast === 'function' ? showToast : window.bkToast)(t); }
  function campo(id, lbl, ctrl) { return '<div class="bk-field"><label class="bk-label" for="' + id + '">' + lbl + '</label>' + ctrl + '</div>'; }

  var PANE =
    '<div id="f-pane-requerimiento" role="tabpanel" aria-labelledby="f-tab-requerimiento" hidden>' +
      '<p class="bk-prosa">Guarda lo que este contacto busca. Broquer lo cruza con tu inventario, el de tu equipo y la Bolsa, y el Buscador lo revisa en internet una vez al día.</p>' +
      '<div class="bk-field-row">' +
        campo('bp-operacion', 'Operación', '<select class="bk-select" id="bp-operacion"><option value="venta">Venta</option><option value="renta">Renta</option></select>') +
        campo('bp-tipo', 'Tipo de propiedad', '<select class="bk-select" id="bp-tipo"><option value="casa">Casa</option></select>') +
      '</div><div class="bk-field-row is-three">' +
        campo('bp-colonia', 'Colonia', '<input class="bk-input" id="bp-colonia" type="text" placeholder="Ej. Altozano"/>') +
        campo('bp-ciudad', 'Ciudad', '<input class="bk-input" id="bp-ciudad" type="text" placeholder="Ej. Morelia"/>') +
        campo('bp-estado', 'Estado', '<input class="bk-input" id="bp-estado" type="text" placeholder="Ej. Michoacán"/>') +
      '</div><div class="bk-field-row is-three">' +
        campo('bp-precio-min', 'Precio mínimo', '<input class="bk-input" id="bp-precio-min" type="number" min="0" placeholder="$"/>') +
        campo('bp-precio-max', 'Precio máximo', '<input class="bk-input" id="bp-precio-max" type="number" min="0" placeholder="$"/>') +
        campo('bp-recamaras', 'Recámaras mínimas', '<input class="bk-input" id="bp-recamaras" type="number" min="0" placeholder="0"/>') +
      '</div>' +
      campo('bp-notas', 'Notas', '<textarea class="bk-input" id="bp-notas" rows="2" placeholder="Cualquier otro detalle que ayude a encontrar lo que busca…"></textarea>') +
      '<div class="bk-acciones"><label class="bk-switch"><input type="checkbox" id="bp-activo" checked/><span class="bk-switch__track"></span> Buscar automáticamente todos los días</label>' +
        '<button class="bk-btn bk-btn--sm" id="bp-guardar" onclick="bpGuardarRequerimiento()">Guardar requerimiento</button></div>' +
      '<div class="bk-bloque" id="bp-resultados-bloque"><div class="bk-acciones"><h3 class="bk-acciones__t" id="bp-resultados-titulo">Encontrado en internet</h3>' +
        '<button class="bk-btn bk-btn--ghost bk-btn--sm" id="bp-buscar-ahora" onclick="bpBuscarAhora()">Buscar ahora</button></div><div id="bp-resultados-feed"></div></div>' +
    '</div>';
  var TAB = '<button class="bk-tab" id="f-tab-requerimiento" role="tab" aria-selected="false" aria-controls="f-pane-requerimiento" onclick="setDetTab(\'requerimiento\')">' +
    'Requerimiento <span class="bk-tab__n" id="f-n-requerimiento" hidden></span></button>';

  window.frqMontar = function () {
    if (el('f-pane-requerimiento')) return;   // vista Pipeline: ya existe
    var tabT = el('f-tab-tareas'), paneT = el('f-pane-tareas');
    if (!tabT || !paneT) return;
    tabT.insertAdjacentHTML('afterend', TAB);
    paneT.insertAdjacentHTML('afterend', PANE);
    if (window.bkCat) el('bp-tipo').innerHTML = window.bkCat.tiposOptions('casa');
    if (typeof setDetTab === 'function' && !setDetTab.__frq) {
      var orig = setDetTab;
      setDetTab = function (tab) {
        var pane = el('f-pane-requerimiento'), btn = el('f-tab-requerimiento');
        if (tab === 'requerimiento') {
          ['info', 'bitacora', 'props', 'tareas'].forEach(function (t) {
            var p = el('f-pane-' + t), b = el('f-tab-' + t);
            if (p) p.hidden = true;
            if (b) { b.classList.remove('is-active'); b.setAttribute('aria-selected', 'false'); }
          });
          pane.hidden = false; btn.classList.add('is-active'); btn.setAttribute('aria-selected', 'true');
          try { detTabActual = 'requerimiento'; } catch (e) {}
          window.bpCargarRequerimiento();
          return;
        }
        if (pane) pane.hidden = true;
        if (btn) { btn.classList.remove('is-active'); btn.setAttribute('aria-selected', 'false'); }
        return orig.apply(this, arguments);
      };
      setDetTab.__frq = true;
    }
  };

  // En la vista Pipeline estas funciones ya existen (clientes-ficha.js).
  if (typeof window.bpCargarRequerimiento === 'function') return;

  function fechaHora(iso) {
    try { return new Date(iso).toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; }
  }
  function render(resultados, ultima) {
    el('bp-resultados-titulo').textContent = 'Encontrado en internet' + (ultima ? ' · última lectura ' + fechaHora(ultima) : '');
    el('bp-resultados-feed').innerHTML = (resultados || []).length
      ? resultados.map(function (r) {
          var precio = r.precio ? ' · $' + Number(r.precio).toLocaleString('es-MX') + (r.precio_confirmado ? '' : ' (sin confirmar)') : '';
          return '<div class="bk-fila"><span class="bk-fila__ico"><svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><circle cx="11" cy="11" r="8"/><path stroke-linecap="round" d="M21 21l-4.35-4.35"/></svg></span>' +
            '<a class="bk-fila__cuerpo" href="' + esc(r.url) + '" target="_blank" rel="noopener noreferrer"><span class="bk-fila__t">' + esc(r.titulo || r.portal || 'Ver anuncio') + '</span>' +
            '<span class="bk-fila__d">' + esc(r.portal || '') + precio + '</span></a></div>';
        }).join('')
      : '<div class="bk-vacio"><h3>Todavía no hay enlaces</h3><p>Guarda el requerimiento o presiona "Buscar ahora" para la primera lectura.</p></div>';
    if (typeof bkContador === 'function') bkContador('f-n-requerimiento', (resultados || []).length);
  }
  window.bpCargarRequerimiento = async function () {
    if (typeof detContacto === 'undefined' || !detContacto) return;
    var id = encodeURIComponent(detContacto.id);
    el('bp-resultados-feed').innerHTML = '<div class="bk-cargando"></div>';
    try {
      var res = await Promise.all([window.bkApi('/api/buscador/requerimiento/' + id), window.bkApi('/api/buscador/resultados/' + id)]);
      var req = res[0] || {}, datos = res[1] || {};
      put('bp-operacion', req.operacion || 'venta'); put('bp-tipo', req.tipo_inmueble || 'casa');
      put('bp-colonia', req.colonia); put('bp-ciudad', req.ciudad); put('bp-estado', req.estado);
      put('bp-precio-min', req.precio_min || ''); put('bp-precio-max', req.precio_max || '');
      put('bp-recamaras', req.recamaras_min || ''); put('bp-notas', req.notas);
      el('bp-activo').checked = req.activo !== false;
      render(datos.resultados, (datos.requerimiento || {}).ultima_busqueda_en);
    } catch (e) {
      el('bp-resultados-feed').innerHTML = '<div class="bk-vacio"><h3>No se pudo cargar</h3><p>' + esc(e.message || '') + '</p></div>';
    }
  };
  window.bpGuardarRequerimiento = async function () {
    if (typeof detContacto === 'undefined' || !detContacto) return;
    var btn = el('bp-guardar'); btn.disabled = true; btn.textContent = 'Guardando…';
    var body = {
      activo: el('bp-activo').checked, operacion: val('bp-operacion') || 'venta', tipo_inmueble: val('bp-tipo') || 'casa',
      colonia: val('bp-colonia'), ciudad: val('bp-ciudad'), estado: val('bp-estado'),
      precio_min: Number(val('bp-precio-min')) || 0, precio_max: Number(val('bp-precio-max')) || 0,
      recamaras_min: Number(val('bp-recamaras')) || 0, notas: val('bp-notas'),
    };
    try {
      await window.bkApi('/api/buscador/requerimiento/' + encodeURIComponent(detContacto.id), { method: 'PUT', json: body });
      toast('Requerimiento guardado');
      if (body.activo && body.colonia) await window.bpBuscarAhora();
    } catch (e) { toast(e.message || 'No se pudo guardar el requerimiento'); }
    finally { btn.disabled = false; btn.textContent = 'Guardar requerimiento'; }
  };
  window.bpBuscarAhora = async function () {
    if (typeof detContacto === 'undefined' || !detContacto) return;
    var id = encodeURIComponent(detContacto.id);
    var btn = el('bp-buscar-ahora'); btn.disabled = true; btn.textContent = 'Buscando…';
    el('bp-resultados-feed').innerHTML = '<div class="bk-cargando"></div>';
    try {
      await window.bkApi('/api/buscador/escanear/' + id, { method: 'POST' });
      var datos = await window.bkApi('/api/buscador/resultados/' + id);
      render(datos.resultados, (datos.requerimiento || {}).ultima_busqueda_en);
    } catch (e) {
      el('bp-resultados-feed').innerHTML = '<div class="bk-vacio"><h3>No se pudo buscar</h3><p>' + esc(e.message || '') + '</p></div>';
    } finally { btn.disabled = false; btn.textContent = 'Buscar ahora'; }
  };
})();
