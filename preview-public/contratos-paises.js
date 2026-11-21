/* ══════════════════════════════════════════════════════════════════
   Contratos fuera de México (Colombia, Perú, Argentina y Chile).

   El formulario de contratos.html es el mismo para todos; aquí se le
   cambian las etiquetas al vocabulario del país, se agrega la moneda y
   se avisa que el modelo debe revisarlo un abogado local. Los contratos
   en sí los arma contratos_paises.py en el servidor.
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var VOCAB = {
    CO: { garante: 'Deudor solidario', registro: 'Matrícula inmobiliaria', tomo: 'Oficina de registro (ciudad)',
          notario: 'Nombre del notario', notaria: 'Número de notaría', arrendador: 'Arrendador', arrendatario: 'Arrendatario' },
    PE: { garante: 'Fiador solidario', registro: 'Partida electrónica', tomo: 'Zona registral',
          notario: 'Nombre del notario', notaria: 'Número de notaría', arrendador: 'Arrendador', arrendatario: 'Arrendatario' },
    AR: { garante: 'Fiador', registro: 'Matrícula', tomo: 'Registro de la Propiedad de (provincia)',
          notario: 'Nombre del escribano', notaria: 'Número de registro notarial', arrendador: 'Locador', arrendatario: 'Locatario' },
    CL: { garante: 'Aval y codeudor solidario', registro: 'Fojas, número y año de inscripción', tomo: 'Conservador de Bienes Raíces de',
          notario: 'Nombre del notario', notaria: 'Número de notaría', arrendador: 'Arrendador', arrendatario: 'Arrendatario' },
  };

  function pais() { return window.bkPais ? bkPais() : 'MX'; }

  // Cambia solo el primer texto de la etiqueta (conserva los badges).
  function etiqueta(id, texto) {
    var el = document.getElementById(id);
    var f = el && el.closest('.f');
    var lbl = f && f.querySelector('label');
    if (!lbl) return;
    for (var i = 0; i < lbl.childNodes.length; i++) {
      var n = lbl.childNodes[i];
      if (n.nodeType === 3 && n.textContent.trim()) {
        if (!lbl.dataset.mx) lbl.dataset.mx = n.textContent;
        n.textContent = texto + ' ';
        return;
      }
    }
  }
  function cadaId(patron, texto, ejemplo) {
    document.querySelectorAll('[id^="a-"], [id^="p-"]').forEach(function (el) {
      if (!patron.test(el.id)) return;
      etiqueta(el.id, texto);
      if (ejemplo && el.placeholder && !/defecto/i.test(el.placeholder)) el.placeholder = ejemplo;
    });
  }
  function textos(selector, de, a) {
    document.querySelectorAll(selector).forEach(function (el) {
      if (el.textContent.indexOf(de) !== -1) el.textContent = el.textContent.split(de).join(a);
    });
  }

  function selectorMoneda(cfg) {
    if (document.getElementById('ct-moneda')) return;
    var picker = document.querySelector('.doc-picker');
    if (!picker) return;
    var box = document.createElement('div');
    box.className = 'f';
    box.style.margin = '0 0 var(--sp-4)';
    box.innerHTML = '<label for="ct-moneda">Moneda del contrato</label>';
    var sel = document.createElement('select');
    sel.id = 'ct-moneda';
    cfg.monedas.forEach(function (m) {
      var o = document.createElement('option');
      o.value = m; o.textContent = m;
      sel.appendChild(o);
    });
    sel.addEventListener('change', function () { aplicarMoneda(sel.value); });
    box.appendChild(sel);
    var nota = document.createElement('div');
    nota.className = 'f-note';
    nota.textContent = 'Modelo de contrato para ' + cfg.nombre + ' conforme a su legislación. Revísalo con un abogado local antes de firmarlo.';
    box.appendChild(nota);
    picker.parentNode.insertBefore(box, picker.nextSibling);
  }

  function aplicarMoneda(m) {
    document.querySelectorAll('label').forEach(function (l) {
      l.childNodes.forEach(function (n) {
        if (n.nodeType === 3) n.textContent = n.textContent.replace(/\((MXN|COP|PEN|ARS|CLP|UF|USD|\$)\)/, '(' + m + ')');
      });
    });
  }

  function aplicar() {
    var c = pais();
    var v = VOCAB[c];
    if (!v || !window.bkPaisCfg) return;
    var cfg = bkPaisCfg(c);
    cadaId(/colonia/, cfg.zona, cfg.zona);
    cadaId(/-estado-(inm|arr|os|inm-os|vend|comp)$/, cfg.region, cfg.region);
    cadaId(/-estado-firma$/, cfg.region + ' de firma');
    cadaId(/municipio/, 'Ciudad / Municipio', 'Ciudad o municipio');
    textos('.f-note', 'Los tribunales competentes y el Código Civil aplicable se determinan por el Estado de firma; si se deja vacío, se usa el del inmueble.',
      'En este modelo, el contrato se rige por la ley de ' + cfg.nombre + ' y son competentes los jueces del lugar del inmueble.');
    cadaId(/-cp(-|$)/, cfg.codigoPostal);
    etiqueta('p-estado-notaria', 'Ciudad de la notaría');
    etiqueta('p-registro', v.registro);
    etiqueta('p-tomo', v.tomo);
    etiqueta('p-not-nombre', v.notario);
    etiqueta('p-not-num', v.notaria);
    etiqueta('a-os', 'Nombre completo del ' + v.garante.toLowerCase());
    textos('.card-title', 'Obligado solidario', v.garante);
    textos('.card-title', 'obligado solidario', v.garante.toLowerCase());
    textos('.card-title', 'Arrendador (propietario)', v.arrendador + ' (propietario)');
    textos('.card-title', 'Arrendatario (inquilino)', v.arrendatario + ' (inquilino)');
    textos('.card-title', 'Datos de escritura pública del vendedor', 'Título de propiedad del vendedor');
    textos('.doc-menu-sub', 'Formato estándar de Broquer', 'Formato de Broquer para ' + cfg.nombre);
    selectorMoneda(cfg);
    aplicarMoneda(document.getElementById('ct-moneda') ? document.getElementById('ct-moneda').value : cfg.monedas[0]);
  }

  // Lo llama generarContrato() antes de mandar los datos al servidor.
  window.bkContratoAjustar = function (datos) {
    var sel = document.getElementById('ct-moneda');
    if (sel && pais() !== 'MX') datos.moneda = sel.value;
  };

  document.addEventListener('bk:pais', aplicar);
  if (window.__BK_PAIS) aplicar();
})();
