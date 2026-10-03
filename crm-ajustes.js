// ─────────────────────────────────────────────────────────────────────────
// crm-ajustes.js · Página "Ajustes de CRM" (sólo dueño/administrador)
//
// Pestañas: Etapas del pipeline · Tipos de contacto · Fuentes de captación ·
// Etiquetas · Categorías de tareas. Otras pantallas pueden sumar pestañas con
// window.crmRegistrarPestana({ id, titulo, render }) (p. ej. el Buzón suma
// "Asignación de leads" y "Respuestas guardadas").
//
// Todo escribe por el backend (routers/crm.py); aquí sólo se pinta.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var esc = window.bkEsc;
  var api = window.bkApi;
  var toast = window.bkToast;
  var CAT = { etapas: [], tipos: [], fuentes: [], es_admin: false };
  var actual = 'etapas';
  var PESTANAS = [
    { id: 'etapas', titulo: 'Etapas del pipeline', render: renderEtapas },
    { id: 'tipos', titulo: 'Tipos de contacto', render: renderTipos },
    { id: 'fuentes', titulo: 'Fuentes de captación', render: renderFuentes },
    { id: 'etiquetas', titulo: 'Etiquetas', render: renderEtiquetas },
    { id: 'categorias', titulo: 'Categorías de tareas', render: renderCategorias },
  ];
  window.crmRegistrarPestana = function (p) { PESTANAS.push(p); pintarTabs(); };
  window.crmCatalogo = function () { return CAT; };

  var SVG_ASA = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="6" r="1.6"/><circle cx="9" cy="12" r="1.6"/><circle cx="15" cy="12" r="1.6"/><circle cx="9" cy="18" r="1.6"/><circle cx="15" cy="18" r="1.6"/></svg>';
  var panel = function () { return document.getElementById('crm-panel'); };

  // ── Modal (bk-overlay del sistema) ──
  function modal(titulo, cuerpo, botones) {
    var ov = document.createElement('div');
    ov.className = 'bk-overlay bk-overlay--sheet crm-modal';
    ov.innerHTML = '<div class="bk-modal" role="dialog" aria-modal="true"><div class="bk-modal__head"><div class="bk-modal__title">' + esc(titulo) +
      '</div></div><div class="bk-modal__body">' + cuerpo + '</div><div class="bk-modal__foot"></div></div>';
    var foot = ov.querySelector('.bk-modal__foot');
    var cerrar = function () { ov.classList.remove('is-open'); setTimeout(function () { ov.remove(); }, 250); };
    (botones || []).concat([{ txt: 'Cancelar', cls: 'bk-btn--ghost', fn: cerrar }]).reverse().forEach(function (b) {
      var btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'bk-btn ' + (b.cls || ''); btn.textContent = b.txt;
      btn.onclick = async function () {
        if (b.fn === cerrar) return cerrar();
        btn.disabled = true;
        try { if ((await b.fn(ov)) !== false) cerrar(); }
        catch (e) { toast(e.message || 'No se pudo completar'); }
        finally { btn.disabled = false; }
      };
      foot.appendChild(btn);
    });
    ov.addEventListener('click', function (e) { if (e.target === ov) cerrar(); });
    document.body.appendChild(ov);
    requestAnimationFrame(function () { ov.classList.add('is-open'); });
    var foco = ov.querySelector('input,select,textarea'); if (foco) setTimeout(function () { foco.focus(); }, 60);
    return ov;
  }
  window.crmModal = modal;
  function pedirTexto(titulo, etiqueta, valor) {
    return new Promise(function (res) {
      modal(titulo, '<div class="bk-field"><label class="bk-label">' + esc(etiqueta) + '</label><input class="bk-input" id="crm-txt" value="' + esc(valor || '') + '" maxlength="60"/></div>',
        [{ txt: 'Guardar', cls: 'bk-btn--forest', fn: function (ov) { var v = ov.querySelector('#crm-txt').value.trim(); if (!v) return false; res(v); } }]);
    });
  }

  async function recargar() {
    try {
      CAT = await api('/crm/catalogos');
      var aviso = document.getElementById('crm-aviso');
      aviso.hidden = CAT.es_admin;
      aviso.textContent = CAT.es_admin ? '' : 'Puedes ver los ajustes, pero sólo el dueño o un administrador de la cuenta los puede cambiar.';
    } catch (e) {
      panel().innerHTML = '<div class="bk-empty"><div class="bk-empty__title">No se pudieron cargar los ajustes</div><div class="bk-empty__text">' + esc(e.message) + '</div></div>';
      return false;
    }
    return true;
  }

  function pintarTabs() {
    var cont = document.getElementById('crm-tabs'); if (!cont) return;
    cont.innerHTML = PESTANAS.map(function (p) {
      return '<button type="button" class="bk-tab' + (p.id === actual ? ' is-active' : '') + '" role="tab" aria-selected="' + (p.id === actual) + '" data-tab="' + p.id + '">' + esc(p.titulo) + '</button>';
    }).join('');
  }
  function abrir(id) {
    actual = id;
    try { history.replaceState(null, '', '#' + id); } catch (e) {}
    pintarTabs();
    var p = PESTANAS.find(function (x) { return x.id === id; }) || PESTANAS[0];
    panel().innerHTML = '<div class="bk-cargando">Cargando…</div>';
    Promise.resolve(p.render(panel(), CAT)).catch(function (e) { panel().innerHTML = '<p>' + esc(e.message) + '</p>'; });
  }
  window.crmAbrir = abrir;

  // ══ Etapas ══
  function colorInput(valor) {
    // Los colores del sistema vienen como var(--…); el selector nativo pide hex.
    var hex = /^#/.test(valor || '') ? valor : getComputedStyle(document.documentElement).getPropertyValue((valor || '').replace(/^var\((--[^)]+)\)$/, '$1')).trim();
    return /^#[0-9a-f]{6}$/i.test(hex) ? hex : '#4f6d8f';
  }
  function renderEtapas(el) {
    var dis = CAT.es_admin ? '' : ' disabled';
    el.innerHTML = '<h2>Etapas del pipeline</h2><p>Arrastra para reordenar. Renombrar no mueve a nadie: cada contacto sigue en su etapa.</p>' +
      '<div class="crm-lista" id="crm-etapas">' + CAT.etapas.map(function (e) {
        return '<div class="crm-fila" draggable="' + CAT.es_admin + '" data-id="' + esc(e.id) + '">' +
          '<span class="crm-asa" aria-hidden="true">' + SVG_ASA + '</span>' +
          '<span class="crm-punto" style="background:' + esc(e.color || 'var(--mute)') + '"></span>' +
          '<span class="crm-nombre">' + esc(e.nombre) + '</span>' +
          '<span class="crm-acciones">' +
            '<input type="color" class="crm-color" aria-label="Color" value="' + colorInput(e.color) + '" data-color="' + esc(e.id) + '"' + dis + '/>' +
            '<button class="bk-btn bk-btn--ghost bk-btn--sm" data-ren="' + esc(e.id) + '"' + dis + '>Renombrar</button>' +
            '<button class="bk-btn bk-btn--danger bk-btn--sm" data-del="' + esc(e.id) + '"' + dis + '>Eliminar</button>' +
          '</span></div>';
      }).join('') + '</div>' +
      (CAT.es_admin ? '<div class="crm-nuevo"><input class="bk-input" id="crm-etapa-nueva" placeholder="Nueva etapa, p. ej. Visita agendada" maxlength="60"/>' +
        '<button class="bk-btn bk-btn--forest" id="crm-etapa-add">Agregar etapa</button></div>' : '');
    var lista = el.querySelector('#crm-etapas');
    lista.onclick = async function (ev) {
      var r = ev.target.closest('[data-ren]'), d = ev.target.closest('[data-del]');
      if (r) {
        var e = CAT.etapas.find(function (x) { return String(x.id) === r.dataset.ren; });
        var nombre = await pedirTexto('Renombrar etapa', 'Nombre', e.nombre);
        await api('/crm/etapas/' + e.id, { method: 'PATCH', json: { nombre: nombre } });
        toast('Etapa renombrada'); await recargar(); abrir('etapas');
      }
      if (d) {
        var et = CAT.etapas.find(function (x) { return String(x.id) === d.dataset.del; });
        var otras = CAT.etapas.filter(function (x) { return x.id !== et.id; });
        modal('Eliminar «' + et.nombre + '»', '<p>¿A qué etapa pasan los contactos que hoy están en «' + esc(et.nombre) + '»?</p>' +
          '<select class="bk-select" id="crm-mover">' + otras.map(function (o) { return '<option value="' + esc(o.clave) + '">' + esc(o.nombre) + '</option>'; }).join('') + '</select>',
          [{ txt: 'Eliminar y mover', cls: 'bk-btn--danger', fn: async function (ov) {
            var r2 = await api('/crm/etapas/' + et.id + '?mover_a=' + encodeURIComponent(ov.querySelector('#crm-mover').value), { method: 'DELETE' });
            toast('Etapa eliminada · ' + (r2.movidos || 0) + ' contactos movidos'); await recargar(); abrir('etapas');
          } }]);
      }
    };
    lista.onchange = async function (ev) {
      var c = ev.target.closest('[data-color]'); if (!c) return;
      await api('/crm/etapas/' + c.dataset.color, { method: 'PATCH', json: { color: c.value } });
      c.closest('.crm-fila').querySelector('.crm-punto').style.background = c.value;
      toast('Color guardado'); recargar();
    };
    if (CAT.es_admin) {
      ordenable(lista, async function (ids) {
        await api('/crm/etapas/orden', { method: 'POST', json: { ids: ids } });
        toast('Orden guardado'); recargar();
      });
      el.querySelector('#crm-etapa-add').onclick = async function () {
        var inp = el.querySelector('#crm-etapa-nueva'); var v = inp.value.trim(); if (!v) return inp.focus();
        try { await api('/crm/etapas', { method: 'POST', json: { nombre: v } }); toast('Etapa agregada'); await recargar(); abrir('etapas'); }
        catch (e) { toast(e.message); }
      };
    }
  }

  // Reordenar arrastrando: mouse (drag & drop) y dedo (pointer events).
  function ordenable(lista, alSoltar) {
    var arrastrando = null;
    function ids() { return Array.prototype.map.call(lista.querySelectorAll('.crm-fila'), function (f) { return f.dataset.id; }); }
    lista.addEventListener('dragstart', function (e) { arrastrando = e.target.closest('.crm-fila'); if (arrastrando) arrastrando.classList.add('is-dragging'); });
    lista.addEventListener('dragover', function (e) {
      e.preventDefault(); var sobre = e.target.closest('.crm-fila'); if (!sobre || !arrastrando || sobre === arrastrando) return;
      var r = sobre.getBoundingClientRect();
      lista.insertBefore(arrastrando, (e.clientY - r.top) > r.height / 2 ? sobre.nextSibling : sobre);
    });
    lista.addEventListener('dragend', function () { if (arrastrando) { arrastrando.classList.remove('is-dragging'); arrastrando = null; alSoltar(ids()); } });
    // Touch: se arrastra desde el asa.
    lista.addEventListener('pointerdown', function (e) {
      var asa = e.target.closest('.crm-asa'); if (!asa || e.pointerType === 'mouse') return;
      var fila = asa.closest('.crm-fila'); fila.classList.add('is-dragging'); e.preventDefault();
      function mover(ev) {
        var bajo = document.elementFromPoint(ev.clientX, ev.clientY); var sobre = bajo && bajo.closest('.crm-fila');
        if (!sobre || sobre === fila || sobre.parentNode !== lista) return;
        var r = sobre.getBoundingClientRect();
        lista.insertBefore(fila, (ev.clientY - r.top) > r.height / 2 ? sobre.nextSibling : sobre);
      }
      function soltar() { fila.classList.remove('is-dragging'); window.removeEventListener('pointermove', mover); window.removeEventListener('pointerup', soltar); alSoltar(ids()); }
      window.addEventListener('pointermove', mover); window.addEventListener('pointerup', soltar);
    });
  }

  // ══ Tipos ══
  function renderTipos(el) {
    var dis = CAT.es_admin ? '' : ' disabled';
    el.innerHTML = '<h2>Tipos de contacto</h2><p>El rol de cada contacto (propietario, comprador, notario…).</p><div class="crm-lista" id="crm-tipos">' +
      CAT.tipos.map(function (t) {
        return '<div class="crm-fila"><span class="crm-nombre">' + esc(t.nombre) + '<small>' + esc(t.clave) + '</small></span><span class="crm-acciones">' +
          '<button class="bk-btn bk-btn--ghost bk-btn--sm" data-ren="' + esc(t.id) + '"' + dis + '>Renombrar</button>' +
          (t.clave === 'otro' ? '' : '<button class="bk-btn bk-btn--danger bk-btn--sm" data-del="' + esc(t.id) + '"' + dis + '>Eliminar</button>') + '</span></div>';
      }).join('') + '</div>' +
      (CAT.es_admin ? '<div class="crm-nuevo"><input class="bk-input" id="crm-tipo-nuevo" placeholder="Nuevo tipo, p. ej. Desarrollador" maxlength="60"/><button class="bk-btn bk-btn--forest" id="crm-tipo-add">Agregar tipo</button></div>' : '');
    el.querySelector('#crm-tipos').onclick = async function (ev) {
      var r = ev.target.closest('[data-ren]'), d = ev.target.closest('[data-del]');
      if (r) {
        var t = CAT.tipos.find(function (x) { return String(x.id) === r.dataset.ren; });
        var nombre = await pedirTexto('Renombrar tipo', 'Nombre', t.nombre);
        await api('/crm/tipos/' + t.id, { method: 'PATCH', json: { nombre: nombre } }); toast('Tipo renombrado'); await recargar(); abrir('tipos');
      }
      if (d) {
        var tt = CAT.tipos.find(function (x) { return String(x.id) === d.dataset.del; });
        var otros = CAT.tipos.filter(function (x) { return x.id !== tt.id; });
        modal('Eliminar «' + tt.nombre + '»', '<p>¿Qué tipo tendrán los contactos que hoy son «' + esc(tt.nombre) + '»?</p><select class="bk-select" id="crm-mover">' +
          otros.map(function (o) { return '<option value="' + esc(o.clave) + '"' + (o.clave === 'otro' ? ' selected' : '') + '>' + esc(o.nombre) + '</option>'; }).join('') + '</select>',
          [{ txt: 'Eliminar', cls: 'bk-btn--danger', fn: async function (ov) {
            var r2 = await api('/crm/tipos/' + tt.id + '?mover_a=' + encodeURIComponent(ov.querySelector('#crm-mover').value), { method: 'DELETE' });
            toast('Tipo eliminado · ' + (r2.movidos || 0) + ' contactos actualizados'); await recargar(); abrir('tipos');
          } }]);
      }
    };
    var add = el.querySelector('#crm-tipo-add');
    if (add) add.onclick = async function () {
      var v = el.querySelector('#crm-tipo-nuevo').value.trim(); if (!v) return;
      try { await api('/crm/tipos', { method: 'POST', json: { nombre: v } }); toast('Tipo agregado'); await recargar(); abrir('tipos'); } catch (e) { toast(e.message); }
    };
  }

  // ══ Fuentes ══
  function renderFuentes(el) {
    var dis = CAT.es_admin ? '' : ' disabled';
    el.innerHTML = '<h2>Fuentes de captación</h2><p>Un catálogo único para que "facebook", "Facebook" y "FB" no cuenten como tres. Para juntar dos, márcalas y usa <strong>Fusionar</strong>: todos sus contactos y leads pasan a la que elijas.</p>' +
      '<div class="crm-lista" id="crm-fuentes">' + CAT.fuentes.map(function (f) {
        return '<label class="crm-fila"><input type="checkbox" class="crm-check" value="' + esc(f.id) + '"' + dis + '/><span class="crm-nombre">' + esc(f.nombre) + '</span><span class="crm-acciones">' +
          '<button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" data-ren="' + esc(f.id) + '"' + dis + '>Renombrar</button>' +
          '<button type="button" class="bk-btn bk-btn--danger bk-btn--sm" data-del="' + esc(f.id) + '"' + dis + '>Eliminar</button></span></label>';
      }).join('') + '</div>' +
      '<div class="crm-nuevo"><input class="bk-input" id="crm-fuente-nueva" placeholder="Nueva fuente, p. ej. Inmuebles24" maxlength="80"/><button class="bk-btn bk-btn--forest" id="crm-fuente-add">Agregar fuente</button></div>' +
      (CAT.es_admin ? '<div class="crm-barra"><button class="bk-btn" id="crm-fusionar" disabled>Fusionar seleccionadas</button><span class="crm-sub" id="crm-fus-n" style="margin:0"></span></div>' : '');
    var lista = el.querySelector('#crm-fuentes');
    function sel() { return Array.prototype.map.call(lista.querySelectorAll('.crm-check:checked'), function (c) { return c.value; }); }
    lista.onchange = function () {
      var b = el.querySelector('#crm-fusionar'); if (!b) return;
      var n = sel().length; b.disabled = n < 2; el.querySelector('#crm-fus-n').textContent = n ? n + ' seleccionadas' : '';
    };
    lista.onclick = async function (ev) {
      var r = ev.target.closest('[data-ren]'), d = ev.target.closest('[data-del]');
      if (!r && !d) return;
      ev.preventDefault();
      if (r) {
        var f = CAT.fuentes.find(function (x) { return String(x.id) === r.dataset.ren; });
        var nombre = await pedirTexto('Renombrar fuente', 'Nombre', f.nombre);
        try { await api('/crm/fuentes/' + f.id, { method: 'PATCH', json: { nombre: nombre } }); toast('Fuente renombrada'); await recargar(); abrir('fuentes'); } catch (e) { toast(e.message); }
      }
      if (d) {
        if (!confirm('¿Eliminar esta fuente?')) return;
        try { await api('/crm/fuentes/' + d.dataset.del, { method: 'DELETE' }); toast('Fuente eliminada'); await recargar(); abrir('fuentes'); } catch (e) { toast(e.message); }
      }
    };
    el.querySelector('#crm-fuente-add').onclick = async function () {
      var v = el.querySelector('#crm-fuente-nueva').value.trim(); if (!v) return;
      try { await api('/crm/fuentes', { method: 'POST', json: { nombre: v } }); toast('Fuente agregada'); await recargar(); abrir('fuentes'); } catch (e) { toast(e.message); }
    };
    var fus = el.querySelector('#crm-fusionar');
    if (fus) fus.onclick = function () {
      var ids = sel(); var opciones = CAT.fuentes.filter(function (f) { return ids.indexOf(String(f.id)) !== -1; });
      modal('Fusionar ' + ids.length + ' fuentes', '<p>¿Cuál se queda? Las demás desaparecen y sus contactos y leads pasan a ésta.</p><select class="bk-select" id="crm-destino">' +
        opciones.map(function (o) { return '<option value="' + esc(o.id) + '">' + esc(o.nombre) + '</option>'; }).join('') + '</select>',
        [{ txt: 'Fusionar', cls: 'bk-btn--forest', fn: async function (ov) {
          var destino = ov.querySelector('#crm-destino').value;
          var r = await api('/crm/fuentes/fusionar', { method: 'POST', json: { destino_id: destino, origen_ids: ids.filter(function (i) { return i !== destino; }) } });
          toast('Fusionadas · ' + (r.reasignados || 0) + ' registros reasignados'); await recargar(); abrir('fuentes');
        } }]);
    };
  }

  // ══ Etiquetas ══
  var tablaEt = 'contactos';
  async function renderEtiquetas(el) {
    var datos = await api('/crm/etiquetas?tabla=' + tablaEt);
    var lista = datos.etiquetas || [];
    var dis = CAT.es_admin ? '' : ' disabled';
    el.innerHTML = '<h2>Etiquetas</h2><p>Renombrar a un nombre que ya existe las fusiona.</p>' +
      '<div class="bk-seg" style="margin-bottom:var(--sp-4)">' +
        '<button class="bk-seg__btn' + (tablaEt === 'contactos' ? ' is-active' : '') + '" data-t="contactos">De contactos</button>' +
        '<button class="bk-seg__btn' + (tablaEt === 'propiedades' ? ' is-active' : '') + '" data-t="propiedades">De inmuebles</button></div>' +
      (lista.length ? '<div class="crm-lista" id="crm-et">' + lista.map(function (t) {
        return '<div class="crm-fila"><span class="crm-nombre">' + esc(t.etiqueta) + '<small>' + t.n + (t.n == 1 ? ' registro' : ' registros') + '</small></span><span class="crm-acciones">' +
          '<button class="bk-btn bk-btn--ghost bk-btn--sm" data-ren="' + esc(t.etiqueta) + '"' + dis + '>Renombrar / fusionar</button>' +
          '<button class="bk-btn bk-btn--danger bk-btn--sm" data-del="' + esc(t.etiqueta) + '"' + dis + '>Eliminar</button></span></div>';
      }).join('') + '</div>' : '<div class="bk-empty"><div class="bk-empty__title">Todavía no hay etiquetas</div></div>');
    el.querySelectorAll('[data-t]').forEach(function (b) { b.onclick = function () { tablaEt = b.dataset.t; abrir('etiquetas'); }; });
    var cont = el.querySelector('#crm-et');
    if (cont) cont.onclick = async function (ev) {
      var r = ev.target.closest('[data-ren]'), d = ev.target.closest('[data-del]');
      if (r) {
        var nuevo = await pedirTexto('Renombrar «' + r.dataset.ren + '»', 'Nuevo nombre (si ya existe, se fusionan)', r.dataset.ren);
        var x = await api('/crm/etiquetas/renombrar', { method: 'POST', json: { tabla: tablaEt, de: r.dataset.ren, a: nuevo } });
        toast((x.actualizados || 0) + ' registros actualizados'); abrir('etiquetas');
      }
      if (d) {
        if (!confirm('¿Quitar la etiqueta «' + d.dataset.del + '» de todos los registros?')) return;
        var y = await api('/crm/etiquetas/eliminar', { method: 'POST', json: { tabla: tablaEt, de: d.dataset.del } });
        toast('Etiqueta eliminada de ' + (y.actualizados || 0) + ' registros'); abrir('etiquetas');
      }
    };
  }

  // ══ Categorías de tareas (organizacion_categorias) ══
  async function renderCategorias(el) {
    var orgId = null;
    try { var o = await api('/org'); orgId = o.org_id; } catch (e) {}
    var cats = (orgId && window.brokrSb) ? await window.brokrSb.rest('organizacion_categorias?select=id,nombre&org_id=eq.' + encodeURIComponent(orgId) + '&order=nombre.asc') : [];
    var dis = CAT.es_admin ? '' : ' disabled';
    el.innerHTML = '<h2>Categorías de tareas y notas</h2><p>Las mismas que eliges al crear una tarea o una nota. Cualquier miembro puede crear nuevas desde la tarea; aquí se renombran o se quitan.</p>' +
      ((cats || []).length ? '<div class="crm-lista" id="crm-cats">' + cats.map(function (c) {
        return '<div class="crm-fila"><span class="crm-nombre">' + esc(c.nombre) + '</span><span class="crm-acciones">' +
          '<button class="bk-btn bk-btn--ghost bk-btn--sm" data-ren="' + esc(c.id) + '" data-n="' + esc(c.nombre) + '"' + dis + '>Renombrar</button>' +
          '<button class="bk-btn bk-btn--danger bk-btn--sm" data-del="' + esc(c.id) + '"' + dis + '>Eliminar</button></span></div>';
      }).join('') + '</div>' : '<div class="bk-empty"><div class="bk-empty__title">Aún no hay categorías</div><div class="bk-empty__text">Créalas desde una tarea.</div></div>');
    var cont = el.querySelector('#crm-cats');
    if (cont) cont.onclick = async function (ev) {
      var r = ev.target.closest('[data-ren]'), d = ev.target.closest('[data-del]');
      if (r) { var n = await pedirTexto('Renombrar categoría', 'Nombre', r.dataset.n); await api('/crm/categorias/' + r.dataset.ren, { method: 'PATCH', json: { nombre: n } }); toast('Categoría renombrada'); abrir('categorias'); }
      if (d) { if (!confirm('¿Eliminar esta categoría? Las tareas no se borran.')) return; await api('/crm/categorias/' + d.dataset.del, { method: 'DELETE' }); toast('Categoría eliminada'); abrir('categorias'); }
    };
  }

  document.getElementById('crm-tabs').addEventListener('click', function (e) {
    var b = e.target.closest('[data-tab]'); if (b) abrir(b.dataset.tab);
  });
  (async function () {
    var h = (location.hash || '').replace('#', '');
    if (PESTANAS.some(function (p) { return p.id === h; })) actual = h;
    pintarTabs();
    if (await recargar()) abrir(actual);
  })();
})();
