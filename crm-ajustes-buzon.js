// ─────────────────────────────────────────────────────────────────────────
// crm-ajustes-buzon.js · Pestañas del Buzón dentro de Ajustes de CRM:
//   · Asignación de leads: manual, al agente del inmueble, ruleta o guardias
//     (calendario por día y horario), más la liga del webhook de entrada
//     para Zapier / EasyBroker / portales.
//   · Respuestas guardadas: catálogo con variables {nombre} e {inmueble}.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var esc = window.bkEsc, api = window.bkApi, toast = window.bkToast;
  var DIAS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
  var API = window.API_BASE || 'https://api.broquer.app';
  function esperar() {
    return new Promise(function (r) { (function t() { if (window.crmRegistrarPestana) r(); else setTimeout(t, 30); })(); });
  }

  async function renderAsignacion(el, CAT) {
    if (!CAT.es_admin) { el.innerHTML = '<h2>Asignación de leads</h2><p>Sólo el dueño o un administrador puede cambiar cómo se reparten los leads.</p>'; return; }
    var datos = await api('/buzon/reglas');
    var miembros = ((await api('/org/miembros')).miembros || []).filter(function (m) { return m.activo !== false; });
    var r = datos.regla || {}, guardias = datos.guardias || [];
    var modos = [
      ['manual', 'Manual', 'Los leads llegan sin asignar y alguien los reparte (como trabajan hoy).'],
      ['agente_inmueble', 'Al agente del inmueble', 'Si el lead viene de un inmueble, se asigna a su agente asignado (o a quien lo capturó).'],
      ['ruleta', 'Ruleta', 'Se reparten por turnos entre las personas que elijas.'],
      ['guardias', 'Guardias', 'Se asigna a quien esté de guardia según el calendario. Si nadie está de guardia, queda sin asignar.'],
    ];
    function filaGuardia(gd) {
      gd = gd || { user_id: (miembros[0] || {}).user_id, dia: 1, hora_inicio: '09:00', hora_fin: '18:00' };
      return '<div class="crm-fila crm-guardia">' +
        '<select class="bk-select" data-k="user_id">' + miembros.map(function (m) { return '<option value="' + esc(m.user_id) + '"' + (m.user_id === gd.user_id ? ' selected' : '') + '>' + esc(m.nombre || m.email) + '</option>'; }).join('') + '</select>' +
        '<select class="bk-select" data-k="dia">' + DIAS.map(function (d, i) { return '<option value="' + i + '"' + (i === Number(gd.dia) ? ' selected' : '') + '>' + d + '</option>'; }).join('') + '</select>' +
        '<input class="bk-input" type="time" data-k="hora_inicio" value="' + esc(String(gd.hora_inicio).slice(0, 5)) + '" aria-label="Desde"/>' +
        '<input class="bk-input" type="time" data-k="hora_fin" value="' + esc(String(gd.hora_fin).slice(0, 5)) + '" aria-label="Hasta"/>' +
        '<button type="button" class="crm-btn-x" aria-label="Quitar" onclick="this.parentNode.remove()">×</button></div>';
    }
    el.innerHTML = '<h2>Asignación de leads</h2><p>Cómo se reparte lo que entra al Buzón. Al asignar, el agente recibe un aviso en la app y en el web.</p>' +
      '<div class="crm-lista">' + modos.map(function (m) {
        return '<label class="crm-fila"><input type="radio" name="modo" value="' + m[0] + '" class="crm-check"' + (r.modo === m[0] ? ' checked' : '') + '/>' +
          '<span class="crm-nombre">' + m[1] + '<small>' + m[2] + '</small></span></label>';
      }).join('') + '</div>' +
      '<div id="crm-ruleta" class="crm-sec"><div class="crm-sub">Personas en la ruleta</div><div class="crm-lista">' + miembros.map(function (m) {
        return '<label class="crm-fila"><input type="checkbox" class="crm-check" value="' + esc(m.user_id) + '"' + ((r.ruleta_usuarios || []).indexOf(m.user_id) !== -1 ? ' checked' : '') + '/><span class="crm-nombre">' + esc(m.nombre || m.email) + '</span></label>';
      }).join('') + '</div></div>' +
      '<div id="crm-guardias" class="crm-sec"><div class="crm-sub">Calendario de guardias (hora de México)</div><div class="crm-lista" id="crm-guardias-lista">' +
        guardias.map(filaGuardia).join('') + '</div><button type="button" class="bk-btn bk-btn--quiet bk-btn--sm" id="crm-guardia-add">+ Agregar guardia</button></div>' +
      '<div class="crm-barra"><button class="bk-btn bk-btn--forest" id="crm-reglas-ok">Guardar asignación</button></div>' +
      '<div class="crm-sec"><h2 style="font-size:var(--fs-h5)">Leads de Zapier, EasyBroker y portales</h2>' +
        '<p class="crm-sub">En Zapier usa la acción <strong>Webhooks → POST</strong> a esta liga con los campos <code>nombre</code>, <code>telefono</code>, <code>email</code>, <code>mensaje</code>, <code>fuente</code> y <code>propiedad</code> (ID de EasyBroker o clave interna). Caen al Buzón con su fuente y su inmueble.</p>' +
        '<div class="crm-nuevo"><input class="bk-input" id="crm-webhook" readonly value="' + (r.token_entrada ? esc(API + '/buzon/entrada/' + r.token_entrada) : 'Se genera al guardar') + '"/>' +
        '<button class="bk-btn bk-btn--ghost" id="crm-webhook-copiar">Copiar</button><button class="bk-btn bk-btn--danger" id="crm-webhook-nuevo">Generar otra</button></div></div>';
    function visibilidad() {
      var modo = (el.querySelector('input[name=modo]:checked') || {}).value;
      el.querySelector('#crm-ruleta').hidden = modo !== 'ruleta';
      el.querySelector('#crm-guardias').hidden = modo !== 'guardias';
    }
    visibilidad();
    el.querySelectorAll('input[name=modo]').forEach(function (i) { i.onchange = visibilidad; });
    el.querySelector('#crm-guardia-add').onclick = function () { el.querySelector('#crm-guardias-lista').insertAdjacentHTML('beforeend', filaGuardia()); };
    async function guardar(generar) {
      var modo = (el.querySelector('input[name=modo]:checked') || {}).value || 'manual';
      var ruleta = Array.prototype.map.call(el.querySelectorAll('#crm-ruleta input:checked'), function (c) { return c.value; });
      var gs = Array.prototype.map.call(el.querySelectorAll('.crm-guardia'), function (f) {
        var o = {}; f.querySelectorAll('[data-k]').forEach(function (i) { o[i.dataset.k] = i.value; }); o.dia = Number(o.dia); return o;
      });
      var res = await api('/buzon/reglas', { method: 'PUT', json: { modo: modo, ruleta_usuarios: ruleta, guardias: gs, generar_token: !!generar } });
      if (res.regla && res.regla.token_entrada) el.querySelector('#crm-webhook').value = API + '/buzon/entrada/' + res.regla.token_entrada;
      toast(generar ? 'Liga nueva generada: actualízala en Zapier' : 'Asignación guardada');
    }
    el.querySelector('#crm-reglas-ok').onclick = function () { guardar(false).catch(function (e) { toast(e.message); }); };
    el.querySelector('#crm-webhook-nuevo').onclick = function () {
      if (confirm('La liga actual dejará de funcionar. ¿Generar otra?')) guardar(true).catch(function (e) { toast(e.message); });
    };
    el.querySelector('#crm-webhook-copiar').onclick = function () {
      var v = el.querySelector('#crm-webhook').value;
      (navigator.clipboard ? navigator.clipboard.writeText(v) : Promise.reject()).then(function () { toast('Liga copiada'); }).catch(function () { el.querySelector('#crm-webhook').select(); });
    };
  }

  async function renderRespuestas(el) {
    var lista = (await api('/buzon/respuestas')).respuestas || [];
    var canales = { todos: 'WhatsApp y correo', whatsapp: 'Sólo WhatsApp', correo: 'Sólo correo' };
    el.innerHTML = '<h2>Respuestas guardadas</h2><p>Textos listos para contestar desde el Buzón. Usa <code>{nombre}</code> y <code>{inmueble}</code> y se llenan solos.</p>' +
      '<div class="crm-lista" id="crm-resp">' + (lista.length ? lista.map(function (r) {
        return '<div class="crm-fila"><span class="crm-nombre">' + esc(r.titulo) + '<small>' + esc(canales[r.canal] || '') + ' · ' + esc(r.texto.slice(0, 90)) + (r.texto.length > 90 ? '…' : '') + '</small></span>' +
          '<span class="crm-acciones"><button class="bk-btn bk-btn--ghost bk-btn--sm" data-ed="' + esc(r.id) + '">Editar</button><button class="bk-btn bk-btn--danger bk-btn--sm" data-del="' + esc(r.id) + '">Eliminar</button></span></div>';
      }).join('') : '<div class="crm-sub">Aún no hay respuestas guardadas.</div>') + '</div>' +
      '<button class="bk-btn bk-btn--forest" id="crm-resp-add">Nueva respuesta</button>';
    function editor(r) {
      r = r || { titulo: '', texto: 'Hola {nombre}, gracias por tu interés en {inmueble}. ', canal: 'todos' };
      window.crmModal(r.id ? 'Editar respuesta' : 'Nueva respuesta',
        '<div class="bk-field"><label class="bk-label">Título</label><input class="bk-input" id="rr-t" maxlength="80" value="' + esc(r.titulo) + '"/></div>' +
        '<div class="bk-field"><label class="bk-label">Texto</label><textarea class="bk-input" id="rr-x" rows="5">' + esc(r.texto) + '</textarea></div>' +
        '<div class="bk-field"><label class="bk-label">Dónde se usa</label><select class="bk-select" id="rr-c">' + Object.keys(canales).map(function (k) { return '<option value="' + k + '"' + (k === r.canal ? ' selected' : '') + '>' + canales[k] + '</option>'; }).join('') + '</select></div>',
        [{ txt: 'Guardar', cls: 'bk-btn--forest', fn: async function (ov) {
          var body = { titulo: ov.querySelector('#rr-t').value, texto: ov.querySelector('#rr-x').value, canal: ov.querySelector('#rr-c').value };
          await api('/buzon/respuestas' + (r.id ? '/' + r.id : ''), { method: r.id ? 'PATCH' : 'POST', json: body });
          toast('Respuesta guardada'); window.crmAbrir('respuestas');
        } }]);
    }
    el.querySelector('#crm-resp-add').onclick = function () { editor(); };
    el.querySelector('#crm-resp').onclick = async function (ev) {
      var e = ev.target.closest('[data-ed]'), d = ev.target.closest('[data-del]');
      if (e) editor(lista.find(function (x) { return x.id === e.dataset.ed; }));
      if (d && confirm('¿Eliminar esta respuesta?')) { await api('/buzon/respuestas/' + d.dataset.del, { method: 'DELETE' }); toast('Respuesta eliminada'); window.crmAbrir('respuestas'); }
    };
  }

  esperar().then(function () {
    window.crmRegistrarPestana({ id: 'asignacion', titulo: 'Asignación de leads', render: renderAsignacion });
    window.crmRegistrarPestana({ id: 'respuestas', titulo: 'Respuestas guardadas', render: renderRespuestas });
  });
})();
