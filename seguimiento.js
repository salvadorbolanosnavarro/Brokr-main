// ─────────────────────────────────────────────────────────────────────────
// seguimiento.js · Seguimiento automático (piloto privado)
//   Hoy         prospectos calientes, quién contestó y lo último que salió.
//   Secuencias  toques con plantillas aprobadas que se detienen al contestar.
//   Avisos      bajadas de precio y coincidencias nuevas.
//   Ajustes     horario, tope diario, resumen y plantillas recomendadas.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var esc = window.bkEsc, api = window.bkApi, toast = window.bkToast;
  var $ = function (id) { return document.getElementById(id); };
  var S = { numeros: [], plantillas: {}, secuencias: [], ajustes: null, editando: null, inscribiendo: null, contactos: [], elegidos: {} };
  var COMODINES = [['{nombre}', 'Nombre del contacto'], ['{agente}', 'Tu nombre'], ['{zona}', 'Tu zona']];
  var PIE = 'Responde BAJA si ya no quieres recibir mensajes.';
  var PACK = [
    { nombre: 'seg_primer_contacto', uso: 'Primer toque', vars: ['{nombre}', '{agente}'], ejemplo: ['Juan', 'Salvador'],
      cuerpo: 'Hola {{1}}, soy {{2}}. Vi que te interesó una propiedad y quiero ayudarte a encontrar la ideal. ¿Te mando fotos, precio y ubicación por aquí?' },
    { nombre: 'seg_opciones', uso: 'Segundo toque', vars: ['{nombre}'], ejemplo: ['Juan'],
      cuerpo: 'Hola {{1}}, tengo opciones nuevas que pueden interesarte. Si me dices tu zona y presupuesto, te mando solo lo que sí te sirve. ¿Te parece?' },
    { nombre: 'seg_pregunta_directa', uso: 'Tercer toque', vars: ['{nombre}'], ejemplo: ['Juan'],
      cuerpo: 'Hola {{1}}, ¿sigues buscando inmueble o ya lo resolviste? Con una palabra me ayudas a no escribirte de más.' },
    { nombre: 'seg_cierre_ciclo', uso: 'Último toque', vars: ['{nombre}'], ejemplo: ['Juan'],
      cuerpo: 'Hola {{1}}, no te quiero saturar, así que este es mi último mensaje por ahora. Si retomas tu búsqueda, aquí estoy para ayudarte. Que tengas excelente día.' },
    { nombre: 'seg_bajo_precio', uso: 'Aviso: bajó de precio', vars: [], ejemplo: ['Juan', 'Casa en Tres Marías', '$3,500,000 MXN', 'https://api.broquer.app/p/ejemplo'],
      cuerpo: 'Hola {{1}}, buenas noticias: {{2}} bajó de precio y ahora está en {{3}}. Aquí puedes ver los detalles: {{4}} ¿Te gustaría visitarla?' },
    { nombre: 'seg_nueva_opcion', uso: 'Aviso: nueva opción', vars: [], ejemplo: ['Juan', 'Casa en Tres Marías', '$3,500,000 MXN', 'https://api.broquer.app/p/ejemplo'],
      cuerpo: 'Hola {{1}}, acaba de salir una opción que coincide con lo que buscas: {{2}}, en {{3}}. Aquí tienes los detalles: {{4}} ¿Quieres que te cuente más?' }
  ];
  var RECETA = [
    { dias: 1, plantilla: 'seg_primer_contacto', variables: ['{nombre}', '{agente}'] },
    { dias: 2, plantilla: 'seg_opciones', variables: ['{nombre}'] },
    { dias: 3, plantilla: 'seg_pregunta_directa', variables: ['{nombre}'] },
    { dias: 5, plantilla: 'seg_cierre_ciclo', variables: ['{nombre}'] }
  ];
  var ESTADOS = {
    activa: ['En curso', 'info'], pausada: ['Pausada', 'warn'], respondio: ['Contestó', 'success'],
    terminada: ['Terminó', 'forest'], baja: ['No quiere mensajes', 'danger'], error: ['Error', 'danger'],
    pendiente: ['Pendiente', 'info'], enviando: ['Enviando', 'info'], enviado: ['Avisado', 'success'],
    omitido: ['Omitido', 'warn'], fallido: ['Falló', 'danger']
  };

  // ── utilidades ─────────────────────────────────────────────────────────
  function hace(iso) {
    if (!iso) return '';
    var s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 3600) return 'hace ' + Math.max(1, Math.round(s / 60)) + ' min';
    if (s < 86400) return 'hace ' + Math.round(s / 3600) + ' h';
    var d = Math.round(s / 86400);
    return d === 1 ? 'ayer' : 'hace ' + d + ' días';
  }
  function fecha(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('es-MX', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  }
  function badge(estado) {
    var e = ESTADOS[estado] || [estado, 'info'];
    return '<span class="bk-badge bk-badge--' + e[1] + '">' + esc(e[0]) + '</span>';
  }
  function alerta(host, tipo, texto) {
    $(host).innerHTML = texto ? '<div class="bk-alert bk-alert--' + tipo + '" role="' + (tipo === 'error' ? 'alert' : 'status') + '" style="margin-bottom:var(--sp-4)">' + esc(texto) + '</div>' : '';
  }
  function vacio(titulo, texto) {
    return '<div class="bk-vacio"><h3>' + esc(titulo) + '</h3><p>' + esc(texto) + '</p></div>';
  }
  function numeroNombre(id) {
    var n = S.numeros.find(function (x) { return x.id === id; });
    return n ? (n.alias || n.display_number || 'Número') : 'Número';
  }
  function abrir(id) { $(id).classList.add('is-open'); }
  function cerrar(id) { $(id).classList.remove('is-open'); }
  function contarVars(cuerpo) {
    var m = (cuerpo || '').match(/\{\{\s*(\d+)\s*\}\}/g) || [];
    return m.reduce(function (max, v) { return Math.max(max, parseInt(v.replace(/\D/g, ''), 10)); }, 0);
  }
  function horas(sel, valor, desde, hasta) {
    var h = '';
    for (var i = desde; i <= hasta; i++) h += '<option value="' + i + '"' + (i === valor ? ' selected' : '') + '>' + (i < 10 ? '0' : '') + i + ':00</option>';
    $(sel).innerHTML = h;
  }

  // ── carga base ─────────────────────────────────────────────────────────
  async function plantillasDe(numeroId, forzar) {
    if (!numeroId) return [];
    if (S.plantillas[numeroId] && !forzar) return S.plantillas[numeroId];
    try {
      var d = await api('/whatsapp2/plantillas?numero_id=' + encodeURIComponent(numeroId));
      S.plantillas[numeroId] = d.plantillas || [];
    } catch (e) { S.plantillas[numeroId] = []; }
    return S.plantillas[numeroId];
  }
  function aprobadas(lista) { return (lista || []).filter(function (p) { return p.estatus === 'APPROVED'; }); }

  async function iniciar() {
    try {
      var acceso = await api('/seguimiento/acceso');
      if (!acceso.piloto) {
        document.querySelector('.sg-scroll').innerHTML = vacio('Módulo en piloto privado', 'El seguimiento automático todavía no está disponible para tu cuenta.');
        return;
      }
    } catch (e) { alerta('sg-aviso', 'error', e.message); return; }
    try { S.numeros = ((await api('/whatsapp2/numeros')).numeros || []).filter(function (n) { return n.es_mio; }); } catch (e) { S.numeros = []; }
    if (!S.numeros.length) alerta('sg-aviso', 'warn', 'Conecta un número de WhatsApp en el módulo WhatsApp para poder mandar seguimiento.');
    cargarHoy();
    cargarAjustes();
  }

  // ── Hoy ────────────────────────────────────────────────────────────────
  function metrica(etiqueta, valor) {
    return '<div class="bk-metric"><span class="bk-metric__label">' + esc(etiqueta) + '</span><span class="bk-metric__value">' + esc(valor) + '</span></div>';
  }
  async function cargarHoy() {
    try {
      var d = await api('/seguimiento/resumen');
      var k = d.kpis;
      $('sg-kpis').innerHTML = metrica('En secuencia', k.activos) + metrica('Enviados hoy', k.enviados_hoy) +
        metrica('Contestaron en 7 días', k.respondieron_7d) + metrica('Tasa de respuesta', k.tasa_respuesta == null ? '—' : k.tasa_respuesta + '%');
      $('sg-calientes').innerHTML = d.calientes.length ? d.calientes.map(function (c) {
        return '<article class="sg-lead"><div class="sg-anillo" style="--p:' + c.puntaje + '" aria-label="Puntaje ' + c.puntaje + ' de 100"><span>' + c.puntaje + '</span></div>' +
          '<div style="min-width:0"><div class="sg-lead__nombre">' + esc(c.nombre) + '</div>' +
          (c.ultimo_mensaje ? '<div class="sg-lead__msg">“' + esc(c.ultimo_mensaje) + '”</div>' : '') +
          '<div class="sg-chips">' + c.razones.map(function (r) { return '<span class="bk-chip">' + esc(r) + '</span>'; }).join('') + '</div></div>' +
          '<a class="bk-btn bk-btn--forest" href="whatsapp.html?c=' + encodeURIComponent(c.conversacion_id) + '#chats">Abrir chat</a></article>';
      }).join('') : vacio('Nadie urgente por ahora', 'Cuando alguien escriba seguido, pida visita o conteste tu seguimiento, aparece aquí primero.');
      $('sg-respuestas').innerHTML = d.respuestas.length ? d.respuestas.map(function (r) {
        return '<div class="bk-fila"><div class="bk-fila__cuerpo"><span class="bk-fila__t">' + esc(r.nombre) + '</span><span class="bk-fila__d">Contestó ' + esc(hace(r.respondio_en)) + '</span></div></div>';
      }).join('') : vacio('Todavía nadie', 'Aquí verás a quien conteste uno de tus toques.');
      $('sg-actividad').innerHTML = d.actividad.length ? d.actividad.map(function (e) {
        var tipo = e.tipo === 'toque' ? 'Toque' : e.tipo === 'precio' ? 'Bajó de precio' : 'Nueva opción';
        return '<div class="bk-fila"><div class="bk-fila__cuerpo"><span class="bk-fila__t">' + esc(e.nombre) + '</span><span class="bk-fila__d' + (e.estado === 'fallido' ? ' bk-fila__d--alerta' : '') + '">' +
          esc(tipo + ' · ' + (e.plantilla || '') + ' · ' + hace(e.created_at)) + (e.error ? ' · ' + esc(e.error) : '') + '</span></div>' + badge(e.estado === 'enviado' ? 'enviado' : 'fallido') + '</div>';
      }).join('') : vacio('Sin envíos esta semana', 'Cuando salga el primer toque lo verás aquí.');
    } catch (e) {
      alerta('sg-aviso', 'error', e.message);
      $('sg-calientes').innerHTML = '';
    }
  }

  // ── Secuencias ─────────────────────────────────────────────────────────
  async function cargarSecuencias() {
    try {
      S.secuencias = (await api('/seguimiento/secuencias')).secuencias || [];
    } catch (e) { $('sg-secuencias').innerHTML = ''; alerta('sg-aviso', 'error', e.message); return; }
    if (!S.secuencias.length) {
      $('sg-secuencias').innerHTML = '<div class="bk-empty"><div class="bk-empty__title">Arma tu primera secuencia</div>' +
        '<div class="bk-empty__text">La receta recomendada son 4 toques en 11 días: primer contacto, opciones, pregunta directa y cierre de ciclo. Se detiene sola cuando te contestan.</div>' +
        '<button type="button" class="bk-btn bk-btn--forest bk-empty__action" id="sg-receta">Usar la receta recomendada</button></div>';
      $('sg-receta').onclick = function () { abrirEditor(null, true); };
      return;
    }
    $('sg-secuencias').innerHTML = '<div class="sg-secuencias">' + S.secuencias.map(function (s) {
      var c = s.conteo || {};
      var dias = 0;
      var toques = (s.pasos || []).map(function (p, i) { dias += p.dias; return '<span class="bk-chip">' + (i + 1) + ' · día ' + dias + '</span>'; }).join('');
      return '<article class="bk-card bk-card--pad sg-sec"><div class="sg-sec__head"><div><h3>' + esc(s.nombre) + '</h3>' +
        '<div class="sg-fila-sub">' + esc(numeroNombre(s.numero_id)) + ' · ' + (s.pasos || []).length + ' toques' + (s.auto_leads_nuevos ? ' · inscribe leads nuevos' : '') + '</div></div>' +
        '<label class="bk-switch" title="Activa"><input type="checkbox" data-activa="' + s.id + '"' + (s.activa ? ' checked' : '') + ' aria-label="Secuencia activa"/><span class="bk-switch__track"></span></label></div>' +
        '<div class="sg-toques">' + toques + '</div>' +
        '<div class="sg-conteo"><div><b>' + (c.activa || 0) + '</b><span>En curso</span></div><div><b>' + (c.respondio || 0) + '</b><span>Contestaron</span></div>' +
        '<div><b>' + (c.terminada || 0) + '</b><span>Terminaron</span></div><div><b>' + ((c.error || 0) + (c.baja || 0)) + '</b><span>Sin enviar</span></div></div>' +
        '<div class="sg-acciones"><button type="button" class="bk-btn bk-btn--forest bk-btn--sm" data-inscribir="' + s.id + '">Inscribir contactos</button>' +
        '<button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" data-inscritos="' + s.id + '">Ver inscritos</button>' +
        '<button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" data-editar="' + s.id + '">Editar</button>' +
        '<button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" data-borrar="' + s.id + '">Borrar</button></div></article>';
    }).join('') + '</div>';
  }
  function secuencia(id) { return S.secuencias.find(function (s) { return s.id === id; }); }

  $('sg-secuencias').addEventListener('click', async function (ev) {
    var b = ev.target.closest('button');
    if (!b) return;
    if (b.dataset.editar) abrirEditor(secuencia(b.dataset.editar));
    if (b.dataset.inscribir) abrirInscribir(secuencia(b.dataset.inscribir));
    if (b.dataset.inscritos) abrirInscritos(secuencia(b.dataset.inscritos));
    if (b.dataset.borrar) {
      var s = secuencia(b.dataset.borrar);
      if (!window.confirm('¿Borrar «' + s.nombre + '»? Sus inscritos dejan de recibir toques.')) return;
      try { await api('/seguimiento/secuencias/' + s.id, { method: 'DELETE' }); toast('Secuencia borrada'); cargarSecuencias(); }
      catch (e) { toast(e.message); }
    }
  });
  $('sg-secuencias').addEventListener('change', async function (ev) {
    var id = ev.target.dataset.activa;
    if (!id) return;
    try {
      await api('/seguimiento/secuencias/' + id, { method: 'PATCH', json: { activa: ev.target.checked } });
      toast(ev.target.checked ? 'Secuencia activa' : 'Secuencia en pausa');
    } catch (e) { ev.target.checked = !ev.target.checked; toast(e.message); }
  });

  // ── Editor de secuencia ────────────────────────────────────────────────
  function opcionesNumero(sel, valor) {
    $(sel).innerHTML = S.numeros.map(function (n) {
      return '<option value="' + esc(n.id) + '"' + (n.id === valor ? ' selected' : '') + '>' + esc(n.alias || n.display_number || 'Número') + '</option>';
    }).join('') || '<option value="">Sin números conectados</option>';
  }
  async function abrirEditor(s, receta) {
    S.editando = s ? JSON.parse(JSON.stringify(s)) : {
      nombre: receta ? 'Leads que se enfriaron' : '', numero_id: (S.numeros[0] || {}).id || '', activa: true,
      auto_leads_nuevos: false, hora_envio: 10, pasos: receta ? JSON.parse(JSON.stringify(RECETA)) : [{ dias: 1, plantilla: '', variables: [] }]
    };
    $('ed-titulo').textContent = s ? 'Editar secuencia' : 'Nueva secuencia';
    $('ed-nombre').value = S.editando.nombre;
    opcionesNumero('ed-numero', S.editando.numero_id);
    horas('ed-hora', S.editando.hora_envio || 10, 8, 20);
    $('ed-auto').checked = !!S.editando.auto_leads_nuevos;
    $('ed-activa').checked = S.editando.activa !== false;
    alerta('ed-error', '', '');
    ayudaDias();
    abrir('sg-editor');
    await pintarPasos();
  }
  function ayudaDias() {
    $('ed-ayuda-dias').textContent = $('ed-auto').checked
      ? 'Los días del primer toque son los días de silencio antes de escribirle. Los demás cuentan desde el toque anterior.'
      : 'Los días cuentan desde el toque anterior. El primero cuenta desde que inscribes al contacto (0 = hoy mismo).';
  }
  async function pintarPasos() {
    var lista = aprobadas(await plantillasDe($('ed-numero').value));
    var host = $('ed-pasos');
    if (!lista.length) {
      host.innerHTML = '<div class="bk-alert bk-alert--warn" style="margin-bottom:var(--sp-3)">Este número todavía no tiene plantillas aprobadas por Meta. En Ajustes puedes mandar a aprobación las recomendadas.</div>';
    } else host.innerHTML = '';
    S.editando.pasos.forEach(function (p, i) {
      var elegida = lista.find(function (t) { return t.nombre === p.plantilla; });
      var n = elegida ? contarVars(elegida.cuerpo) : 0;
      var vars = '';
      for (var v = 0; v < n; v++) {
        var actual = p.variables[v] || '';
        var esComodin = COMODINES.some(function (c) { return c[0] === actual; });
        vars += '<div class="bk-field"><label class="bk-label">Dato {{' + (v + 1) + '}}</label><select class="bk-select" data-var="' + i + ':' + v + '">' +
          COMODINES.map(function (c) { return '<option value="' + c[0] + '"' + (c[0] === actual ? ' selected' : '') + '>' + c[1] + '</option>'; }).join('') +
          '<option value="__texto"' + (!esComodin && actual ? ' selected' : '') + '>Texto fijo…</option></select>' +
          (!esComodin && actual ? '<input class="bk-input" style="margin-top:var(--sp-2)" data-fijo="' + i + ':' + v + '" value="' + esc(actual) + '"/>' : '') + '</div>';
      }
      host.insertAdjacentHTML('beforeend', '<div class="sg-paso"><div class="sg-paso__head"><b>Toque ' + (i + 1) + '</b>' +
        (S.editando.pasos.length > 1 ? '<button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" data-quitar="' + i + '">Quitar</button>' : '') + '</div>' +
        '<div class="sg-paso__grid"><div class="bk-field"><label class="bk-label">' + (i === 0 ? 'Días' : 'Días después') + '</label>' +
        '<input class="bk-input" type="number" min="0" max="60" inputmode="numeric" data-dias="' + i + '" value="' + p.dias + '"/></div>' +
        '<div class="bk-field"><label class="bk-label">Plantilla</label><select class="bk-select" data-plantilla="' + i + '"><option value="">Elige una plantilla aprobada</option>' +
        lista.map(function (t) { return '<option value="' + esc(t.nombre) + '"' + (t.nombre === p.plantilla ? ' selected' : '') + '>' + esc(t.nombre) + '</option>'; }).join('') +
        (p.plantilla && !elegida ? '<option value="' + esc(p.plantilla) + '" selected>' + esc(p.plantilla) + ' (no aprobada)</option>' : '') + '</select></div></div>' +
        (elegida ? '<div class="sg-vista">' + esc(elegida.cuerpo) + '</div>' : '') +
        (vars ? '<div class="sg-vars">' + vars + '</div>' : '') + '</div>');
    });
  }
  function leerPasos() {
    var lista = aprobadas(S.plantillas[$('ed-numero').value]);
    S.editando.pasos.forEach(function (p, i) {
      var d = document.querySelector('[data-dias="' + i + '"]');
      var t = document.querySelector('[data-plantilla="' + i + '"]');
      if (d) p.dias = Math.max(0, Math.min(60, parseInt(d.value || '0', 10) || 0));
      if (t) p.plantilla = t.value;
      var elegida = lista.find(function (x) { return x.nombre === p.plantilla; });
      if (elegida) p.idioma = elegida.idioma;
      var n = elegida ? contarVars(elegida.cuerpo) : 0;
      var vars = [];
      for (var v = 0; v < n; v++) {
        var sel = document.querySelector('[data-var="' + i + ':' + v + '"]');
        var fijo = document.querySelector('[data-fijo="' + i + ':' + v + '"]');
        vars.push(sel && sel.value === '__texto' ? (fijo ? fijo.value.trim() : '') : (sel ? sel.value : '{nombre}'));
      }
      p.variables = vars;
    });
  }
  $('ed-pasos').addEventListener('change', function (ev) {
    if (ev.target.dataset.plantilla !== undefined || ev.target.dataset.var !== undefined) {
      leerPasos();
      if (ev.target.dataset.var && ev.target.value === '__texto') {
        var ij = ev.target.dataset.var.split(':');
        S.editando.pasos[+ij[0]].variables[+ij[1]] = ' ';
      }
      pintarPasos();
    }
  });
  $('ed-pasos').addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-quitar]');
    if (!b) return;
    leerPasos();
    S.editando.pasos.splice(+b.dataset.quitar, 1);
    pintarPasos();
  });
  $('ed-agregar').onclick = function () {
    leerPasos();
    if (S.editando.pasos.length >= 6) { toast('Máximo 6 toques: más que eso ya satura.'); return; }
    S.editando.pasos.push({ dias: 3, plantilla: '', variables: [] });
    pintarPasos();
  };
  $('ed-numero').onchange = function () { leerPasos(); pintarPasos(); };
  $('ed-auto').onchange = ayudaDias;
  $('ed-guardar').onclick = async function () {
    leerPasos();
    var cuerpo = { nombre: $('ed-nombre').value.trim(), numero_id: $('ed-numero').value, activa: $('ed-activa').checked,
      auto_leads_nuevos: $('ed-auto').checked, hora_envio: +$('ed-hora').value,
      pasos: S.editando.pasos.map(function (p) { return { dias: p.dias, plantilla: p.plantilla, idioma: p.idioma || 'es_MX', variables: p.variables }; }) };
    if (cuerpo.pasos.some(function (p) { return !p.plantilla; })) { alerta('ed-error', 'error', 'Cada toque necesita una plantilla aprobada.'); return; }
    if (cuerpo.auto_leads_nuevos && cuerpo.pasos[0].dias < 1) cuerpo.pasos[0].dias = 1;
    var btn = this; btn.disabled = true;
    try {
      if (S.editando.id) await api('/seguimiento/secuencias/' + S.editando.id, { method: 'PATCH', json: cuerpo });
      else await api('/seguimiento/secuencias', { method: 'POST', json: cuerpo });
      cerrar('sg-editor'); toast('Secuencia guardada'); cargarSecuencias();
    } catch (e) { alerta('ed-error', 'error', e.message); }
    finally { btn.disabled = false; }
  };

  // ── Inscribir contactos ────────────────────────────────────────────────
  async function abrirInscribir(s) {
    S.inscribiendo = s; S.elegidos = {};
    $('in-titulo').textContent = 'Inscribir en «' + s.nombre + '»';
    $('in-buscar').value = ''; $('in-todos').checked = false;
    abrir('sg-inscribir');
    try {
      var et = await api('/whatsapp2/etiquetas');
      var lista = et.etiquetas || [];
      $('in-etiqueta').innerHTML = '<option value="">Todas</option>' + lista.map(function (e) {
        var nombre = typeof e === 'string' ? e : (e.nombre || e.etiqueta || '');
        return nombre ? '<option value="' + esc(nombre) + '">' + esc(nombre) + '</option>' : '';
      }).join('');
    } catch (e) { $('in-etiqueta').innerHTML = '<option value="">Todas</option>'; }
    buscarContactos();
  }
  var espera;
  async function buscarContactos() {
    var s = S.inscribiendo;
    $('in-lista').innerHTML = '<div class="bk-cargando">Cargando…</div>';
    try {
      var q = '/seguimiento/contactos?numero_id=' + encodeURIComponent(s.numero_id) + '&q=' + encodeURIComponent($('in-buscar').value) +
        '&etiqueta=' + encodeURIComponent($('in-etiqueta').value);
      S.contactos = (await api(q)).contactos || [];
    } catch (e) { $('in-lista').innerHTML = '<div style="padding:var(--sp-4)">' + esc(e.message) + '</div>'; return; }
    pintarContactos();
  }
  function pintarContactos() {
    $('in-lista').innerHTML = S.contactos.length ? S.contactos.map(function (c) {
      var off = c.opt_out || c.en_secuencia;
      var motivo = c.opt_out ? 'No quiere mensajes' : c.en_secuencia ? 'Ya va en una secuencia' : (c.ultimo_en ? 'Escribió ' + hace(c.ultimo_en) : 'Sin mensajes');
      return '<label class="sg-sel' + (off ? ' is-off' : '') + '"><span class="bk-check"><input type="checkbox" data-c="' + esc(c.id) + '"' +
        (off ? ' disabled' : '') + (S.elegidos[c.id] ? ' checked' : '') + '/><span class="bk-check__box"><svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg></span></span>' +
        '<span class="sg-sel__txt"><b>' + esc(c.nombre || c.wa_id) + '</b><span class="sg-fila-sub">' + esc((c.wa_id || '') + ' · ' + motivo) + '</span></span></label>';
    }).join('') : '<div style="padding:var(--sp-4)" class="sg-ayuda">No hay contactos con ese filtro en este número.</div>';
    contarElegidos();
  }
  function contarElegidos() {
    var n = Object.keys(S.elegidos).length;
    $('in-guardar').disabled = !n;
    $('in-guardar').textContent = n ? 'Inscribir ' + n : 'Inscribir';
  }
  $('in-lista').addEventListener('change', function (ev) {
    var id = ev.target.dataset.c;
    if (!id) return;
    if (ev.target.checked) S.elegidos[id] = true; else delete S.elegidos[id];
    contarElegidos();
  });
  $('in-todos').onchange = function () {
    var on = this.checked;
    S.contactos.forEach(function (c) { if (!c.opt_out && !c.en_secuencia) { if (on) S.elegidos[c.id] = true; else delete S.elegidos[c.id]; } });
    pintarContactos();
  };
  $('in-buscar').oninput = function () { clearTimeout(espera); espera = setTimeout(buscarContactos, 350); };
  $('in-etiqueta').onchange = buscarContactos;
  $('in-guardar').onclick = async function () {
    var btn = this; btn.disabled = true;
    try {
      var r = await api('/seguimiento/secuencias/' + S.inscribiendo.id + '/inscripciones', { method: 'POST', json: { contacto_ids: Object.keys(S.elegidos) } });
      cerrar('sg-inscribir');
      toast(r.inscritos + ' inscrito' + (r.inscritos === 1 ? '' : 's') + (r.omitidos.length ? ' · ' + r.omitidos.length + ' omitido' + (r.omitidos.length === 1 ? '' : 's') : ''));
      cargarSecuencias();
    } catch (e) { toast(e.message); btn.disabled = false; }
  };

  // ── Inscritos ──────────────────────────────────────────────────────────
  async function abrirInscritos(s) {
    S.viendo = s;
    $('li-titulo').textContent = 'Inscritos en «' + s.nombre + '»';
    $('li-lista').innerHTML = '<div class="bk-cargando">Cargando…</div>';
    abrir('sg-inscritos');
    try {
      var filas = (await api('/seguimiento/secuencias/' + s.id + '/inscripciones')).inscripciones || [];
      var total = (s.pasos || []).length;
      $('li-lista').innerHTML = filas.length ? filas.map(function (f) {
        var detalle = f.estado === 'activa' ? 'Toque ' + (f.paso + 1) + ' de ' + total + ' · ' + fecha(f.proximo_en)
          : f.estado === 'respondio' ? 'Contestó ' + hace(f.respondio_en) : (f.motivo || 'Toques enviados: ' + f.paso);
        var accion = f.estado === 'activa' ? '<button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" data-estado="pausada" data-id="' + f.id + '">Pausar</button>'
          : f.estado === 'pausada' ? '<button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" data-estado="activa" data-id="' + f.id + '">Reanudar</button>' : '';
        if (f.estado === 'activa' || f.estado === 'pausada') accion += '<button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" data-estado="terminada" data-id="' + f.id + '">Quitar</button>';
        return '<div class="bk-fila"><div class="bk-fila__cuerpo"><span class="bk-fila__t">' + esc(f.nombre) + '</span><span class="bk-fila__d' + (f.estado === 'error' ? ' bk-fila__d--alerta' : '') + '">' + esc(detalle) + '</span></div>' +
          badge(f.estado) + '<div class="sg-acciones">' + accion + '</div></div>';
      }).join('') : vacio('Sin inscritos', 'Inscribe contactos o activa la inscripción automática de leads nuevos.');
    } catch (e) { $('li-lista').innerHTML = vacio('No se pudo cargar', e.message); }
  }
  $('li-lista').addEventListener('click', async function (ev) {
    var b = ev.target.closest('[data-estado]');
    if (!b) return;
    try {
      await api('/seguimiento/inscripciones/' + b.dataset.id, { method: 'PATCH', json: { estado: b.dataset.estado } });
      abrirInscritos(S.viendo); cargarSecuencias();
    } catch (e) { toast(e.message); }
  });

  // ── Avisos por evento ──────────────────────────────────────────────────
  async function cargarEventos() {
    try {
      var filas = (await api('/seguimiento/eventos')).eventos || [];
      $('sg-eventos').innerHTML = filas.length ? filas.map(function (e) {
        var d = e.detalle || {};
        var que = e.tipo === 'precio' ? 'Bajó de precio: ' + (d.titulo || '') : 'Nueva opción: ' + (d.titulo || '');
        return '<div class="bk-fila"><div class="bk-fila__cuerpo"><span class="bk-fila__t">' + esc(e.nombre) + '</span><span class="bk-fila__d">' +
          esc(que + ' · ' + hace(e.created_at)) + (e.motivo ? ' · ' + esc(e.motivo) : '') + '</span></div>' + badge(e.estado) + '</div>';
      }).join('') : vacio('Sin avisos todavía', 'Broquer revisa cada hora tus inmuebles y los requerimientos de tus clientes.');
    } catch (e) { $('sg-eventos').innerHTML = vacio('No se pudo cargar', e.message); }
  }

  // ── Ajustes y plantillas recomendadas ──────────────────────────────────
  async function cargarAjustes() {
    try { S.ajustes = (await api('/seguimiento/ajustes')).ajustes; }
    catch (e) { alerta('sg-aviso', 'error', e.message); return; }
    var a = S.ajustes;
    opcionesNumero('aj-numero', a.numero_id || (S.numeros[0] || {}).id);
    horas('aj-inicio', a.hora_inicio, 6, 21);
    horas('aj-fin', a.hora_fin, 7, 23);
    $('aj-tope').value = a.tope_diario;
    $('aj-resumen').checked = !!a.resumen_diario;
    $('aj-eventos').checked = !!a.eventos_activos;
    pintarEstado();
    await pintarPlantillasAjustes();
  }
  function pintarEstado() {
    var a = S.ajustes, ahora = new Date(), h = ahora.getHours(), dom = ahora.getDay() === 0;
    var on = !dom && h >= a.hora_inicio && h < a.hora_fin;
    $('sg-estado').innerHTML = '<span class="sg-punto' + (on ? ' is-on' : '') + '"></span><span>' +
      (on ? 'Enviando: los toques salen cada 5 minutos hasta las ' + a.hora_fin + ':00.' : 'Fuera de horario: los envíos salen de lunes a sábado de ' + a.hora_inicio + ':00 a ' + a.hora_fin + ':00.') + '</span>';
  }
  async function pintarPlantillasAjustes(forzar) {
    var numero = $('aj-numero').value;
    var todas = await plantillasDe(numero, forzar);
    var lista = aprobadas(todas);
    var opciones = function (valor) {
      return '<option value="">Sin plantilla</option>' + lista.filter(function (t) { return contarVars(t.cuerpo) === 4; }).map(function (t) {
        return '<option value="' + esc(t.nombre) + '"' + (t.nombre === valor ? ' selected' : '') + '>' + esc(t.nombre) + '</option>';
      }).join('');
    };
    $('aj-precio').innerHTML = opciones(S.ajustes.plantilla_precio || 'seg_bajo_precio');
    $('aj-coincidencia').innerHTML = opciones(S.ajustes.plantilla_coincidencia || 'seg_nueva_opcion');
    var faltan = 0;
    $('sg-pack').innerHTML = PACK.map(function (p) {
      var t = todas.find(function (x) { return x.nombre === p.nombre; });
      var est = !t ? ['Falta', 'warn'] : t.estatus === 'APPROVED' ? ['Aprobada', 'success'] : t.estatus === 'REJECTED' ? ['Rechazada', 'danger'] : ['En revisión', 'info'];
      if (!t) faltan++;
      return '<div class="sg-plantilla"><div><b style="font-size:var(--fs-sm)">' + esc(p.uso) + '</b><p class="sg-ayuda">' + esc(p.cuerpo) + '</p></div><span class="bk-badge bk-badge--' + est[1] + '">' + est[0] + '</span></div>';
    }).join('');
    $('sg-pack-enviar').disabled = !faltan || !numero;
  }
  $('aj-numero').onchange = function () { pintarPlantillasAjustes(); };
  $('aj-guardar').onclick = async function () {
    var btn = this; btn.disabled = true;
    try {
      S.ajustes = (await api('/seguimiento/ajustes', { method: 'PUT', json: {
        numero_id: $('aj-numero').value || null, hora_inicio: +$('aj-inicio').value, hora_fin: +$('aj-fin').value,
        tope_diario: +$('aj-tope').value || 60, resumen_diario: $('aj-resumen').checked, eventos_activos: $('aj-eventos').checked,
        plantilla_precio: $('aj-precio').value || null, plantilla_coincidencia: $('aj-coincidencia').value || null, idioma: 'es_MX'
      } })).ajustes;
      pintarEstado(); toast('Ajustes guardados');
    } catch (e) { toast(e.message); }
    finally { btn.disabled = false; }
  };
  $('sg-pack-enviar').onclick = async function () {
    var numero = $('aj-numero').value, btn = this;
    var todas = await plantillasDe(numero);
    var faltan = PACK.filter(function (p) { return !todas.some(function (x) { return x.nombre === p.nombre; }); });
    btn.disabled = true;
    var ok = 0, errores = [];
    for (var i = 0; i < faltan.length; i++) {
      var p = faltan[i];
      try {
        await api('/whatsapp2/plantillas', { method: 'POST', json: { numero_id: numero, nombre: p.nombre, idioma: 'es_MX', categoria: 'MARKETING', cuerpo: p.cuerpo, variables_ejemplo: p.ejemplo, footer: PIE } });
        ok++;
      } catch (e) { errores.push(p.uso + ': ' + e.message); }
    }
    toast(ok ? ok + ' plantilla' + (ok === 1 ? '' : 's') + ' enviada' + (ok === 1 ? '' : 's') + ' a Meta. La aprobación tarda de minutos a un día.' : 'No se pudo enviar ninguna.');
    if (errores.length) alerta('sg-aviso', 'error', errores.join(' · '));
    await pintarPlantillasAjustes(true);
  };

  // ── pestañas, cierre de modales y "revisar ahora" ──────────────────────
  var cargado = { hoy: true };
  document.querySelector('.sg-tabs').addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-tab]');
    if (!b) return;
    document.querySelectorAll('.sg-tabs .bk-tab').forEach(function (t) {
      var on = t === b; t.classList.toggle('is-active', on); t.setAttribute('aria-selected', String(on));
    });
    document.querySelectorAll('.sg-panel').forEach(function (p) { p.hidden = p.dataset.panel !== b.dataset.tab; });
    var tab = b.dataset.tab;
    if (tab === 'secuencias') cargarSecuencias();
    if (tab === 'avisos') cargarEventos();
    if (tab === 'hoy' && cargado.hoy) cargarHoy();
  });
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-cerrar]');
    if (b) cerrar(b.dataset.cerrar);
    if (ev.target.classList && ev.target.classList.contains('bk-overlay')) cerrar(ev.target.id);
  });
  $('sg-correr').onclick = async function () {
    var btn = this; btn.disabled = true;
    try {
      var r = (await api('/seguimiento/correr', { method: 'POST' })).resultado;
      var partes = [];
      if (r.respuestas) partes.push(r.respuestas + ' contestaron');
      if (r.inscritos) partes.push(r.inscritos + ' inscritos solos');
      if (r.toques) partes.push(r.toques + ' toques enviados');
      if (r.avisos) partes.push(r.avisos + ' avisos enviados');
      if (r.detectados) partes.push(r.detectados + ' eventos nuevos');
      toast(partes.length ? partes.join(' · ') : (r.en_horario ? 'Todo al día: no tocaba enviar nada.' : 'Revisado. Fuera de horario no sale ningún mensaje.'));
      cargarHoy();
    } catch (e) { toast(e.message); }
    finally { btn.disabled = false; }
  };

  iniciar();
})();
