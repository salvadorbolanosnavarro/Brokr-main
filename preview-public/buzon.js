// ─────────────────────────────────────────────────────────────────────────
// buzon.js · Buzón: bandeja única de leads (routers/buzon.py)
//   Lista con estados y filtros · conversación con asignar, nota interna,
//   marcar atendida, respuestas guardadas ({nombre}, {inmueble}) y tiempo de
//   primera respuesta · alta de "lead de teléfono".
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var esc = window.bkEsc, api = window.bkApi, toast = window.bkToast;
  var S = { estado: 'sin_atender', leads: [], activo: null, miembros: [], fuentes: [], props: [], respuestas: [], es_admin: false, yo: null };
  var CANALES = { whatsapp: 'WhatsApp', sitio: 'Sitio web', bolsa: 'Bolsa Broquer', zapier: 'Zapier', easybroker: 'EasyBroker',
    telefono: 'Llamada', manual: 'Captura manual', meta: 'Meta Lead Ads', portal: 'Portal inmobiliario', correo: 'Correo' };
  function g(id) { return document.getElementById(id); }
  function iniciales(n) { var p = String(n || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + ((p[1] || '')[0] || '')).toUpperCase(); }
  function hace(iso) {
    if (!iso) return '';
    var s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return 'ahora'; if (s < 3600) return Math.floor(s / 60) + ' min'; if (s < 86400) return Math.floor(s / 3600) + ' h';
    return new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' });
  }
  function duracion(seg) {
    if (seg == null) return '';
    if (seg < 60) return seg + ' s'; if (seg < 3600) return Math.round(seg / 60) + ' min';
    if (seg < 86400) return (seg / 3600).toFixed(1).replace('.0', '') + ' h'; return Math.round(seg / 86400) + ' d';
  }
  function nombreMiembro(uid) { var m = S.miembros.find(function (x) { return x.user_id === uid; }); return m ? (m.nombre || m.email || 'Agente') : 'Agente'; }
  function aviso() { window.dispatchEvent(new Event('brokr-buzon-cambio')); }

  // ── Lista ──
  async function cargar() {
    var qs = new URLSearchParams({ estado: S.estado });
    [['canal', 'bz-f-canal'], ['fuente_id', 'bz-f-fuente'], ['asignado', 'bz-f-asignado'], ['propiedad_id', 'bz-f-prop']].forEach(function (p) {
      var v = g(p[1]).value; if (v) qs.set(p[0], v);
    });
    try {
      var d = await api('/buzon?' + qs.toString());
      S.leads = d.leads || []; S.es_admin = !!d.es_admin;
    } catch (e) {
      g('bz-items').innerHTML = '<div class="bz-vacio">' + esc(e.message) + '</div>'; return;
    }
    pintarLista();
    if (S.activo && !S.leads.some(function (l) { return l.id === S.activo; }) && window.innerWidth > 860) cerrarDetalle();
  }
  function pintarLista() {
    var cont = g('bz-items');
    if (!S.leads.length) {
      cont.innerHTML = '<div class="bz-vacio"><strong>' + (S.estado === 'sin_atender' ? 'Todo al día' : 'Nada por aquí') + '</strong><p>' +
        (S.estado === 'sin_atender' ? 'Cuando entre un lead de WhatsApp, tu sitio, la Bolsa o Zapier, aparece aquí.' : '') + '</p></div>';
      return;
    }
    cont.innerHTML = S.leads.map(function (l) {
      var chips = '<span class="bz-chip bz-chip--canal">' + esc(CANALES[l.canal] || l.canal) + '</span>';
      if (l.fuente && l.fuente !== CANALES[l.canal]) chips += '<span class="bz-chip">' + esc(l.fuente) + '</span>';
      if (l.propiedad_titulo) chips += '<span class="bz-chip">' + esc(l.propiedad_titulo) + '</span>';
      chips += l.asignado_a ? '<span class="bz-chip">' + esc(nombreMiembro(l.asignado_a)) + '</span>' : '<span class="bz-chip bz-chip--warn">Sin asignar</span>';
      return '<button type="button" class="bz-item' + (l.id === S.activo ? ' is-active' : '') + '" data-id="' + esc(l.id) + '">' +
        '<span class="bz-item__av">' + esc(iniciales(l.nombre || l.telefono)) + '</span><span class="bz-item__cuerpo">' +
        '<span class="bz-item__fila"><span class="bz-item__nombre">' + esc(l.nombre || l.telefono || l.email || 'Sin nombre') + '</span><span class="bz-item__hora">' + esc(hace(l.ultimo_mensaje_en)) + '</span></span>' +
        '<span class="bz-item__msg">' + esc(l.mensaje || '') + '</span><span class="bz-chips">' + chips + '</span></span></button>';
    }).join('');
  }

  // ── Detalle ──
  function cerrarDetalle() { S.activo = null; g('bz-detalle').hidden = true; document.querySelector('.bz').classList.remove('is-detalle'); pintarLista(); }
  function reemplazar(texto, l) {
    return String(texto || '').replace(/\{nombre\}/g, (l.nombre || '').split(' ')[0] || '').replace(/\{inmueble\}/g, l.propiedad_titulo || 'el inmueble');
  }
  async function abrir(id) {
    var l = S.leads.find(function (x) { return x.id === id; });
    if (!l) return;
    S.activo = id; pintarLista();
    document.querySelector('.bz').classList.add('is-detalle');
    var det = g('bz-detalle'); det.hidden = false;
    var esWA = l.canal === 'whatsapp' && l.referencia;
    var asignar = S.es_admin
      ? '<select class="bk-select" id="bz-asignar" aria-label="Asignar a"><option value="">Sin asignar</option>' +
        S.miembros.map(function (m) { return '<option value="' + esc(m.user_id) + '"' + (m.user_id === l.asignado_a ? ' selected' : '') + '>' + esc(m.nombre || m.email || 'Agente') + '</option>'; }).join('') + '</select>'
      : (l.asignado_a ? '<span class="bz-chip">' + esc(nombreMiembro(l.asignado_a)) + '</span>' : '<button class="bk-btn bk-btn--sm" id="bz-tomar">Tomarlo</button>');
    var estadoBtns = (l.estado === 'sin_atender' ? '<button class="bk-btn bk-btn--forest bk-btn--sm" data-estado="atendida">Marcar atendida</button>' :
      '<button class="bk-btn bk-btn--ghost bk-btn--sm" data-estado="sin_atender">Reabrir</button>') +
      (l.estado !== 'archivada' ? '<button class="bk-btn bk-btn--ghost bk-btn--sm" data-estado="archivada">Archivar</button>' : '') +
      (l.estado !== 'spam' ? '<button class="bk-btn bk-btn--danger bk-btn--sm" data-estado="spam">Spam</button>' : '');
    var tel = String(l.telefono || '').replace(/[^\d+]/g, '');
    var datos = [
      l.telefono ? '<div class="bz-dato">Tel. <a href="tel:' + esc(tel) + '">' + esc(l.telefono) + '</a></div>' : '',
      l.email ? '<div class="bz-dato">Correo <a href="mailto:' + esc(l.email) + '">' + esc(l.email) + '</a></div>' : '',
      l.propiedad_id ? '<div class="bz-dato">Inmueble <a href="propiedades.html?id=' + encodeURIComponent(l.propiedad_id) + '" target="_blank">' + esc(l.propiedad_titulo || 'Ver ficha') + '</a></div>' : '',
      l.contacto_id ? '<div class="bz-dato">Contacto <a href="contactos.html?id=' + encodeURIComponent(l.contacto_id) + '">Ver ficha</a></div>' : '',
      '<div class="bz-dato">Entró ' + esc(new Date(l.created_at).toLocaleString('es-MX')) + (l.primera_respuesta_seg != null ? ' · primera respuesta en <strong>' + esc(duracion(l.primera_respuesta_seg)) + '</strong>' : ' · <strong>sin responder</strong>') + '</div>',
    ].join('');
    det.innerHTML = '<div class="bz-det-head">' +
        '<button class="bk-btn bk-btn--ghost bk-btn--sm bz-volver" id="bz-volver">‹ Buzón</button>' +
        '<h2>' + esc(l.nombre || l.telefono || 'Sin nombre') + '</h2>' +
        '<div class="bz-chips"><span class="bz-chip bz-chip--canal">' + esc(CANALES[l.canal] || l.canal) + '</span>' + (l.fuente ? '<span class="bz-chip">' + esc(l.fuente) + '</span>' : '') + '</div>' +
        '<div class="bz-det-acc">' + asignar + estadoBtns + '</div></div>' +
      '<div class="bz-det-cuerpo">' + datos +
        (esWA ? '<div class="bz-hilo" id="bz-hilo"><div class="bk-cargando">Cargando conversación…</div></div>' : (l.mensaje ? '<div class="bz-msg bz-msg--in">' + esc(l.mensaje) + '</div>' : '')) +
        '<div class="bk-field"><label class="bk-label" for="bz-nota">Nota interna (sólo el equipo la ve)</label><textarea class="bk-input" id="bz-nota" rows="2">' + esc(l.nota_interna || '') + '</textarea>' +
        '<button class="bk-btn bk-btn--ghost bk-btn--sm" id="bz-nota-ok" style="align-self:flex-start;margin-top:6px">Guardar nota</button></div>' +
      '</div>' +
      '<div class="bz-composer"><select class="bk-select" id="bz-resp" aria-label="Respuesta guardada"><option value="">Respuesta guardada…</option>' +
        S.respuestas.filter(function (r) { return r.canal === 'todos' || r.canal === (esWA ? 'whatsapp' : 'correo') || !esWA; })
          .map(function (r) { return '<option value="' + esc(r.id) + '">' + esc(r.titulo) + '</option>'; }).join('') + '</select>' +
        '<textarea class="bk-input" id="bz-texto" placeholder="Escribe tu respuesta…"></textarea>' +
        '<div class="bz-composer__fila">' + (esWA
          ? '<button class="bk-btn bk-btn--forest" id="bz-enviar-wa">Enviar por WhatsApp</button>'
          : (tel ? '<button class="bk-btn bk-btn--forest" id="bz-abrir-wa">Abrir en WhatsApp</button>' : '') + (l.email ? '<button class="bk-btn" id="bz-abrir-mail">Enviar por correo</button>' : '')) +
        '</div></div>';
    if (esWA) cargarHilo(l);
    g('bz-volver').onclick = cerrarDetalle;
    det.querySelectorAll('[data-estado]').forEach(function (b) { b.onclick = function () { cambiarEstado(l, b.dataset.estado); }; });
    var sel = g('bz-asignar'); if (sel) sel.onchange = function () { asignarA(l, sel.value || null); };
    var tomar = g('bz-tomar'); if (tomar) tomar.onclick = function () { asignarA(l, S.yo); };
    g('bz-nota-ok').onclick = async function () {
      try { await api('/buzon/' + l.id, { method: 'PATCH', json: { nota_interna: g('bz-nota').value } }); l.nota_interna = g('bz-nota').value; toast('Nota guardada'); } catch (e) { toast(e.message); }
    };
    g('bz-resp').onchange = function () {
      var r = S.respuestas.find(function (x) { return x.id === this.value; }, this);
      if (r) { var t = g('bz-texto'); t.value = (t.value ? t.value + '\n' : '') + reemplazar(r.texto, l); t.focus(); }
      this.value = '';
    };
    var w = g('bz-enviar-wa');
    if (w) w.onclick = async function () {
      var texto = g('bz-texto').value.trim(); if (!texto) return;
      w.disabled = true;
      try {
        await api('/whatsapp2/mensajes', { method: 'POST', json: { conversacion_id: l.referencia, texto: texto } });
        g('bz-texto').value = ''; await marcarRespondido(l); cargarHilo(l);
      } catch (e) { toast(e.message.indexOf('ventana') !== -1 ? 'Pasaron más de 24 h: abre el chat en WhatsApp de Broquer para mandar una plantilla.' : e.message); }
      finally { w.disabled = false; }
    };
    var aw = g('bz-abrir-wa');
    if (aw) aw.onclick = function () {
      var d = tel.replace(/\D/g, ''); if (d.length === 10) d = '52' + d;
      window.open('https://wa.me/' + d + '?text=' + encodeURIComponent(g('bz-texto').value), '_blank'); marcarRespondido(l);
    };
    var am = g('bz-abrir-mail');
    if (am) am.onclick = function () {
      location.href = 'mailto:' + l.email + '?subject=' + encodeURIComponent(l.propiedad_titulo ? 'Sobre ' + l.propiedad_titulo : 'Tu consulta') + '&body=' + encodeURIComponent(g('bz-texto').value);
      marcarRespondido(l);
    };
    try { history.replaceState(null, '', 'buzon.html?id=' + encodeURIComponent(id)); } catch (e) {}
  }
  async function cargarHilo(l) {
    var cont = g('bz-hilo'); if (!cont) return;
    try {
      var d = await api('/whatsapp2/mensajes?conversacion_id=' + encodeURIComponent(l.referencia) + '&limit=40');
      var msgs = Array.isArray(d) ? d : (d.mensajes || d.items || []);
      msgs.sort(function (a, b) { return new Date(a.created_at) - new Date(b.created_at); });
      cont.innerHTML = msgs.length ? msgs.map(function (m) {
        return '<div class="bz-msg bz-msg--' + (m.direction === 'out' ? 'out' : 'in') + '">' + esc(m.body || '') + '<small>' + esc(hace(m.created_at)) + '</small></div>';
      }).join('') : '<div class="bz-dato">Sin mensajes.</div>';
    } catch (e) { cont.innerHTML = '<div class="bz-dato">No se pudo cargar la conversación: ' + esc(e.message) + '</div>'; }
  }
  async function marcarRespondido(l) {
    if (l.primera_respuesta_en) return;
    try { await api('/buzon/' + l.id + '/respondido', { method: 'POST' }); l.primera_respuesta_en = new Date().toISOString(); } catch (e) {}
  }
  async function cambiarEstado(l, estado) {
    try {
      await api('/buzon/' + l.id, { method: 'PATCH', json: { estado: estado } });
      toast({ atendida: 'Marcado como atendido', archivada: 'Archivado', spam: 'Marcado como spam', sin_atender: 'Reabierto' }[estado]);
      aviso(); await cargar(); cerrarDetalle();
    } catch (e) { toast(e.message); }
  }
  async function asignarA(l, uid) {
    try {
      await api('/buzon/' + l.id + '/asignar', { method: 'POST', json: { user_id: uid } });
      l.asignado_a = uid; toast(uid ? 'Asignado a ' + nombreMiembro(uid) : 'Asignación quitada'); pintarLista(); abrir(l.id); aviso();
    } catch (e) { toast(e.message); }
  }

  // ── Alta manual ──
  function altaManual() {
    var ov = document.createElement('div');
    ov.className = 'bk-overlay bk-overlay--sheet crm-modal';
    ov.innerHTML = '<div class="bk-modal" role="dialog" aria-modal="true"><div class="bk-modal__head"><div class="bk-modal__title">Lead de teléfono</div></div>' +
      '<form class="bk-modal__body" onsubmit="return false">' +
        '<div class="bk-field"><label class="bk-label">Nombre *</label><input class="bk-input" name="nombre" required/></div>' +
        '<div class="bk-field"><label class="bk-label">Teléfono</label><input class="bk-input" name="telefono" type="tel" inputmode="tel"/></div>' +
        '<div class="bk-field"><label class="bk-label">Correo</label><input class="bk-input" name="email" type="email"/></div>' +
        '<div class="bk-field"><label class="bk-label">Inmueble de interés</label><select class="bk-select" name="propiedad_id"><option value="">Ninguno</option>' +
          S.props.map(function (p) { return '<option value="' + esc(p.id) + '">' + esc(p.titulo || 'Sin título') + '</option>'; }).join('') + '</select></div>' +
        '<div class="bk-field"><label class="bk-label">Fuente</label><select class="bk-select" name="fuente"><option value="Llamada">Llamada</option>' +
          S.fuentes.map(function (f) { return '<option>' + esc(f.nombre) + '</option>'; }).join('') + '</select></div>' +
        '<div class="bk-field"><label class="bk-label">Qué busca / mensaje</label><textarea class="bk-input" name="mensaje" rows="3"></textarea></div>' +
      '</form><div class="bk-modal__foot"><button class="bk-btn bk-btn--ghost" data-x>Cancelar</button><button class="bk-btn bk-btn--forest" data-ok>Guardar lead</button></div></div>';
    document.body.appendChild(ov);
    requestAnimationFrame(function () { ov.classList.add('is-open'); });
    var cerrar = function () { ov.classList.remove('is-open'); setTimeout(function () { ov.remove(); }, 250); };
    ov.querySelector('[data-x]').onclick = cerrar;
    ov.querySelector('[data-ok]').onclick = async function () {
      var fd = Object.fromEntries(new FormData(ov.querySelector('form')));
      if (!fd.nombre.trim()) return ov.querySelector('[name=nombre]').focus();
      this.disabled = true;
      try {
        var lead = await api('/buzon/manual', { method: 'POST', json: { nombre: fd.nombre, telefono: fd.telefono, email: fd.email, mensaje: fd.mensaje,
          fuente: fd.fuente, canal: 'telefono', propiedad_id: fd.propiedad_id || null } });
        cerrar(); toast('Lead registrado' + (lead.asignado_a ? ' y asignado a ' + nombreMiembro(lead.asignado_a) : ''));
        S.estado = 'sin_atender'; marcarEstado(); aviso(); await cargar();
      } catch (e) { this.disabled = false; toast(e.message); }
    };
  }

  function marcarEstado() { g('bz-estados').querySelectorAll('[data-estado]').forEach(function (b) { b.classList.toggle('is-active', b.dataset.estado === S.estado); }); }

  async function init() {
    g('bz-estados').addEventListener('click', function (e) { var b = e.target.closest('[data-estado]'); if (!b) return; S.estado = b.dataset.estado; marcarEstado(); cargar(); });
    ['bz-f-canal', 'bz-f-fuente', 'bz-f-asignado', 'bz-f-prop'].forEach(function (id) { g(id).onchange = cargar; });
    g('bz-items').addEventListener('click', function (e) { var b = e.target.closest('[data-id]'); if (b) abrir(b.dataset.id); });
    g('bz-nuevo').onclick = altaManual;
    g('bz-f-canal').innerHTML += Object.keys(CANALES).map(function (k) { return '<option value="' + k + '">' + CANALES[k] + '</option>'; }).join('');
    window.addEventListener('brokr-buzon-contador', function (e) { g('bz-n-sin').textContent = e.detail > 0 ? e.detail : ''; });
    var tareas = [
      api('/org').then(function (o) { S.yo = (window.brokrSb && window.brokrSb.userId) || null; S.org = o; }).catch(function () {}),
      api('/org/miembros').then(function (d) { S.miembros = (d.miembros || []).filter(function (m) { return m.activo !== false; }); }).catch(function () {}),
      api('/crm/catalogos').then(function (c) { S.fuentes = c.fuentes || []; }).catch(function () {}),
      api('/buzon/respuestas').then(function (d) { S.respuestas = d.respuestas || []; }).catch(function () {}),
      window.bkRest('propiedades?select=id,titulo&order=titulo.asc&limit=1000')
        .then(function (p) { S.props = Array.isArray(p) ? p : []; }).catch(function () {}),
    ];
    try { var u = JSON.parse(localStorage.getItem('sb_user') || sessionStorage.getItem('sb_user') || '{}'); S.yo = u.id || null; } catch (e) {}
    await Promise.all(tareas);
    g('bz-f-fuente').innerHTML += S.fuentes.map(function (f) { return '<option value="' + esc(f.id) + '">' + esc(f.nombre) + '</option>'; }).join('');
    g('bz-f-prop').innerHTML += S.props.map(function (p) { return '<option value="' + esc(p.id) + '">' + esc(p.titulo || 'Sin título') + '</option>'; }).join('');
    if (S.miembros.length > 1) g('bz-f-asignado').innerHTML += S.miembros.map(function (m) { return '<option value="' + esc(m.user_id) + '">' + esc(m.nombre || m.email) + '</option>'; }).join('');
    await cargar();
    var id = new URLSearchParams(location.search).get('id');
    if (id) {
      if (!S.leads.some(function (l) { return l.id === id; })) {   // puede estar en otro estado
        for (var est of ['atendida', 'archivada', 'spam']) { S.estado = est; await cargar(); if (S.leads.some(function (l) { return l.id === id; })) break; }
        if (!S.leads.some(function (l) { return l.id === id; })) { S.estado = 'sin_atender'; await cargar(); }
        marcarEstado();
      }
      abrir(id);
    }
    setInterval(function () { if (!document.hidden && !S.activo) cargar(); }, 60000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
