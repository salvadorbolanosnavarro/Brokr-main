/* ══════════════════════════════════════════════════════════════════
   Cumplimiento · datos para el aviso oficial de inmuebles (INM).

   El aviso que se sube al SPPLD sigue el XSD oficial de la UIF y usa sus
   catálogos (core/pld/catalogos_inm.json, servidos por /pld/catalogos).
   Aquí se capturan los datos que ese formato pide y que la operación no
   traía: quién compra y quién vende, la otra parte, el inmueble, la
   escritura o contrato y los pagos. El servidor revisa todo otra vez al
   generar el aviso; esta pantalla solo captura.
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var API = 'https://api.broquer.app';
  var CAT = null;
  var LIQ = [];

  function g(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function opciones(nombre, actual, vacio) {
    return (vacio ? '<option value="">' + esc(vacio) + '</option>' : '') +
      ((CAT && CAT[nombre]) || []).map(function (c) {
        return '<option value="' + esc(c[0]) + '"' + (String(actual) === c[0] ? ' selected' : '') + '>' +
          esc(c[1]) + '</option>';
      }).join('');
  }
  function campo(id, etiqueta, html, ancho) {
    return '<div class="bk-field' + (ancho ? ' cp-ancho' : '') + '"><label class="bk-label" for="' + id + '">' +
      esc(etiqueta) + '</label>' + html + '</div>';
  }
  function entrada(id, etiqueta, valor, tipo, extra) {
    return campo(id, etiqueta, '<input class="bk-input" id="' + id + '" type="' + (tipo || 'text') + '"' +
      (extra || '') + ' value="' + esc(valor == null ? '' : valor) + '"/>');
  }
  function lista(id, etiqueta, nombre, actual, vacio, ancho) {
    return campo(id, etiqueta, '<select class="bk-select" id="' + id + '">' + opciones(nombre, actual, vacio) +
      '</select>', ancho);
  }
  function v(id) { var el = g(id); return el ? String(el.value || '').trim() : ''; }
  function num(id) { var x = v(id); return x === '' ? null : Number(x); }

  async function cargarCatalogos() {
    for (var i = 0; i < 60 && !(window.brokrSb && window.brokrSb.ensureToken); i++) {
      await new Promise(function (r) { setTimeout(r, 250); });
    }
    try {
      var tok = await window.brokrSb.ensureToken();
      var r = await fetch(API + '/pld/catalogos', { headers: { Authorization: 'Bearer ' + tok } });
      if (r.ok) CAT = await r.json();
    } catch (e) { /* sin catálogos se queda la captura libre */ }
    if (CAT) convertirExpediente();
  }

  /* ── Expediente: nacionalidad, actividad y giro salen del catálogo UIF ── */
  var EXP_SELECTS = {
    'e-nac': ['pais', 'Elige el país'],
    'e-act': ['actividad_economica', 'Elige del catálogo de la UIF'],
    'e-giro': ['giro_mercantil', 'Elige del catálogo de la UIF']
  };

  function convertirExpediente() {
    Object.keys(EXP_SELECTS).forEach(function (id) {
      var el = g(id);
      if (!el || el.tagName === 'SELECT') return;
      var sel = document.createElement('select');
      sel.className = 'bk-select';
      sel.id = id;
      sel.innerHTML = opciones(EXP_SELECTS[id][0], '', EXP_SELECTS[id][1]);
      el.parentNode.replaceChild(sel, el);
    });
  }

  function paisDe(texto) {
    var t = String(texto || '').trim().toUpperCase();
    if (!t) return '';
    if (/^MEX/.test(t) || t === 'MX') return 'MX';
    var hit = (CAT.pais || []).filter(function (c) { return c[0] === t || c[1] === t; })[0];
    return hit ? hit[0] : '';
  }

  function setExp(exp) {
    if (!CAT) return;
    var valores = {
      'e-nac': paisDe(exp.nacionalidad) || exp.nacionalidad,
      'e-act': exp.actividad_economica,
      'e-giro': exp.giro_mercantil
    };
    Object.keys(valores).forEach(function (id) {
      var sel = g(id), val = valores[id];
      if (!sel || sel.tagName !== 'SELECT') return;
      // Lo capturado antes como texto libre se conserva visible para que el
      // agente elija la clave correcta del catálogo.
      if (val && !sel.querySelector('option[value="' + CSS.escape(String(val)) + '"]')) {
        var o = document.createElement('option');
        o.value = val;
        o.textContent = val + ' (fuera de catálogo: elige una opción)';
        sel.insertBefore(o, sel.options[1] || null);
      }
      sel.value = val || '';
    });
  }

  /* ── Operación: sección del aviso ──────────────────────────────── */
  function pintarLiq() {
    var caja = g('av-liqs');
    if (!caja) return;
    caja.innerHTML = LIQ.map(function (l, i) {
      return '<div class="cp-rejilla" style="border-top:1px solid var(--line);padding-top:var(--sp-3);margin-top:var(--sp-3);">' +
        entrada('av-l-fecha-' + i, 'Fecha del pago ' + (i + 1), l.fecha_pago, 'date') +
        entrada('av-l-monto-' + i, 'Monto', l.monto, 'number', ' step="0.01"') +
        lista('av-l-forma-' + i, 'Forma de pago', 'forma_pago', l.forma_pago, 'Elige') +
        lista('av-l-inst-' + i, 'Instrumento monetario', 'instrumento_monetario', l.instrumento_monetario, 'Elige') +
        lista('av-l-moneda-' + i, 'Moneda', 'moneda', l.moneda || '1', '') +
        '<div class="bk-field" style="align-self:end;"><button class="bk-btn bk-btn--quiet bk-btn--sm" type="button" data-quitar-liq="' + i + '">Quitar pago</button></div>' +
        '</div>';
    }).join('') || '<div class="cp-sub">Sin pagos capturados.</div>';
  }

  function leerLiq() {
    LIQ = LIQ.map(function (l, i) {
      return {
        fecha_pago: v('av-l-fecha-' + i), monto: num('av-l-monto-' + i),
        forma_pago: v('av-l-forma-' + i), instrumento_monetario: v('av-l-inst-' + i),
        moneda: v('av-l-moneda-' + i) || '1'
      };
    });
    return LIQ;
  }

  function alternarInstrumento() {
    var privado = v('av-ins-tipo') === 'contrato';
    g('av-ins-publico').classList.toggle('cp-oculto', privado);
    g('av-ins-contrato').classList.toggle('cp-oculto', !privado);
  }

  function alternarContraparte() {
    var fisica = v('av-c-tipo') !== 'moral';
    ['av-c-nombre-f', 'av-c-ap-f', 'av-c-am-f'].forEach(function (id) {
      g(id).classList.toggle('cp-oculto', !fisica);
    });
    g('av-c-razon-f').classList.toggle('cp-oculto', fisica);
  }

  function pintarOp(op) {
    var caja = g('o-aviso');
    if (!caja) return;
    if (!CAT) { caja.innerHTML = ''; return; }
    var ad = (op && op.aviso_datos) || {};
    var inm = ad.inmueble || {};
    var ins = ad.instrumento || {};
    var c = (ad.contrapartes || [])[0] || {};
    LIQ = (ad.liquidaciones || []).slice();
    if (!LIQ.length && op) {
      LIQ = [{ fecha_pago: String(op.fecha_operacion || '').slice(0, 10), monto: op.monto, moneda: '1' }];
    }

    caja.innerHTML =
      '<details class="cp-bloque" style="margin-top:var(--sp-5);"' + (op ? ' open' : '') + '>' +
      '<summary class="cp-bloque__t" style="cursor:pointer;">Datos para el aviso al SAT</summary>' +
      '<div class="cp-bloque__d">Obligatorios si la operación genera aviso. Son los que pide el formato oficial de la UIF para inmuebles.</div>' +

      '<div class="cp-rejilla">' +
      lista('av-fc', 'El cliente es', 'figura_cliente', ad.figura_cliente, 'Elige') +
      lista('av-fso', 'Tú participas como', 'figura_so', ad.figura_so || '3', '') +
      lista('av-alerta', 'Alerta', 'tipo_alerta', ad.tipo_alerta || '', 'Automática', true) +
      '</div>' +

      '<div class="cp-bloque__t" style="margin-top:var(--sp-5);">La otra parte (vendedor o comprador)</div>' +
      '<div class="cp-rejilla">' +
      campo('av-c-tipo', 'Tipo de persona', '<select class="bk-select" id="av-c-tipo">' +
        '<option value="fisica"' + (c.tipo_persona !== 'moral' ? ' selected' : '') + '>Persona física</option>' +
        '<option value="moral"' + (c.tipo_persona === 'moral' ? ' selected' : '') + '>Persona moral</option></select>') +
      entrada('av-c-rfc', 'RFC (si lo tienes)', c.rfc || c.rfc_moral) +
      '<div id="av-c-nombre-f">' + entrada('av-c-nombre', 'Nombre(s)', c.nombre) + '</div>' +
      '<div id="av-c-ap-f">' + entrada('av-c-ap', 'Apellido paterno', c.apellido_paterno) + '</div>' +
      '<div id="av-c-am-f">' + entrada('av-c-am', 'Apellido materno', c.apellido_materno) + '</div>' +
      '<div id="av-c-razon-f" class="cp-ancho">' + entrada('av-c-razon', 'Razón social', c.razon_social) + '</div>' +
      '</div>' +

      '<div class="cp-bloque__t" style="margin-top:var(--sp-5);">El inmueble</div>' +
      '<div class="cp-rejilla">' +
      lista('av-i-tipo', 'Tipo de inmueble', 'tipo_inmueble', inm.tipo_inmueble, 'Elige') +
      entrada('av-i-valor', 'Valor pactado (MXN)', inm.valor_pactado != null ? inm.valor_pactado : (op ? op.monto : ''), 'number', ' step="0.01"') +
      entrada('av-i-calle', 'Calle', inm.calle) +
      entrada('av-i-next', 'Número exterior', inm.numero_exterior) +
      entrada('av-i-nint', 'Número interior', inm.numero_interior) +
      entrada('av-i-col', 'Colonia', inm.colonia) +
      entrada('av-i-cp', 'Código postal', inm.codigo_postal, 'text', ' maxlength="5" inputmode="numeric"') +
      entrada('av-i-folio', 'Folio real (o XXXX si no tiene)', inm.folio_real) +
      entrada('av-i-terreno', 'm² de terreno', inm.dimension_terreno, 'number', ' step="0.01"') +
      entrada('av-i-const', 'm² de construcción', inm.dimension_construido, 'number', ' step="0.01"') +
      '</div>' +

      '<div class="cp-bloque__t" style="margin-top:var(--sp-5);">Escritura o contrato</div>' +
      '<div class="cp-rejilla">' +
      campo('av-ins-tipo', 'Se formalizó con', '<select class="bk-select" id="av-ins-tipo">' +
        '<option value="publico"' + (ins.tipo !== 'contrato' ? ' selected' : '') + '>Escritura pública</option>' +
        '<option value="contrato"' + (ins.tipo === 'contrato' ? ' selected' : '') + '>Contrato privado</option></select>', true) +
      '</div>' +
      '<div class="cp-rejilla" id="av-ins-publico">' +
      entrada('av-ins-num', 'Número de escritura', ins.numero) +
      entrada('av-ins-fecha', 'Fecha de escritura', ins.fecha, 'date') +
      entrada('av-ins-notario', 'Número de notario', ins.notario) +
      lista('av-ins-entidad', 'Estado del notario', 'entidad_federativa', ins.entidad, 'Elige') +
      entrada('av-ins-avaluo', 'Valor del avalúo catastral', ins.avaluo_catastral, 'number', ' step="0.01"') +
      '</div>' +
      '<div class="cp-rejilla" id="av-ins-contrato">' +
      entrada('av-ins-fcon', 'Fecha del contrato', ins.fecha_contrato, 'date') +
      '</div>' +

      '<div class="cp-bloque__t" style="margin-top:var(--sp-5);">Pagos</div>' +
      '<div class="cp-bloque__d">Uno por cada pago. Si participas como intermediario son opcionales.</div>' +
      '<div id="av-liqs"></div>' +
      '<button class="bk-btn bk-btn--ghost bk-btn--sm" id="av-liq-add" type="button" style="margin-top:var(--sp-3);">Agregar pago</button>' +
      '</details>';

    pintarLiq();
    alternarInstrumento();
    alternarContraparte();
    g('av-ins-tipo').addEventListener('change', alternarInstrumento);
    g('av-c-tipo').addEventListener('change', alternarContraparte);
    g('av-liq-add').addEventListener('click', function () {
      leerLiq();
      LIQ.push({ moneda: '1', fecha_pago: (g('o-fecha') || {}).value || '' });
      pintarLiq();
    });
    g('av-liqs').addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-quitar-liq]');
      if (!b) return;
      leerLiq();
      LIQ.splice(Number(b.getAttribute('data-quitar-liq')), 1);
      pintarLiq();
    });
  }

  function leerOp() {
    if (!g('av-fc')) return undefined;
    var tipoC = v('av-c-tipo');
    var contraparte = tipoC === 'moral'
      ? { tipo_persona: 'moral', razon_social: v('av-c-razon'), rfc_moral: v('av-c-rfc') }
      : { tipo_persona: 'fisica', nombre: v('av-c-nombre'), apellido_paterno: v('av-c-ap'),
          apellido_materno: v('av-c-am'), rfc: v('av-c-rfc') };
    var hayContraparte = contraparte.nombre || contraparte.razon_social;
    return {
      figura_cliente: v('av-fc'), figura_so: v('av-fso'), tipo_alerta: v('av-alerta') || undefined,
      contrapartes: hayContraparte ? [contraparte] : [],
      inmueble: {
        tipo_inmueble: v('av-i-tipo'), valor_pactado: num('av-i-valor'), calle: v('av-i-calle'),
        numero_exterior: v('av-i-next'), numero_interior: v('av-i-nint'), colonia: v('av-i-col'),
        codigo_postal: v('av-i-cp'), folio_real: v('av-i-folio'),
        dimension_terreno: num('av-i-terreno'), dimension_construido: num('av-i-const')
      },
      instrumento: v('av-ins-tipo') === 'contrato'
        ? { tipo: 'contrato', fecha_contrato: v('av-ins-fcon') }
        : { tipo: 'publico', numero: v('av-ins-num'), fecha: v('av-ins-fecha'), notario: v('av-ins-notario'),
            entidad: v('av-ins-entidad'), avaluo_catastral: num('av-ins-avaluo') },
      liquidaciones: leerLiq().filter(function (l) { return l.monto || l.fecha_pago; })
    };
  }

  // Revisión rápida para marcar en la lista las operaciones que aún no se
  // pueden reportar. La revisión completa la hace el servidor al generar.
  function opCompleta(op) {
    var ad = op.aviso_datos || {};
    var inm = ad.inmueble || {};
    var ins = ad.instrumento || {};
    if (!ad.figura_cliente || !inm.tipo_inmueble || !inm.codigo_postal || !inm.calle) return false;
    if ((ad.figura_so || '3') === '3' && !(ad.contrapartes || []).length) return false;
    if (ins.tipo === 'contrato') return !!ins.fecha_contrato;
    return !!(ins.numero && ins.fecha && ins.notario && ins.entidad);
  }

  window.cpAviso = { pintarOp: pintarOp, leerOp: leerOp, setExp: setExp, opCompleta: opCompleta };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', cargarCatalogos);
  else cargarCatalogos();
})();
