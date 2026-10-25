/* ══════════════════════════════════════════════════════════════════
   Cumplimiento (PLD) fuera de México.

   En Colombia, Perú, Argentina y Chile los agentes inmobiliarios también
   son sujetos obligados en prevención de lavado de activos, pero no hay
   aviso en XML al SAT ni UMA. El módulo se queda con lo que aplica en
   cualquier país: expediente del cliente, registro de operaciones con un
   monto de alerta interna, operaciones inusuales y bitácora. El reporte
   de operaciones sospechosas se presenta en el portal de la autoridad.

   El servidor (routers/cumplimiento.py) ya ajusta requisitos y valores
   por defecto; aquí solo se cambian los textos de la pantalla.
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var LEY = {
    CO: { ley: 'el régimen de autocontrol y gestión del riesgo de LA/FT/FPADM (SAGRILAFT) que supervisa la Superintendencia de Sociedades',
          autoridad: 'la UIAF', portal: 'SIREL' },
    PE: { ley: 'la Ley N.º 29038 y la Resolución SBS N.º 789-2018, que incluyen a los agentes inmobiliarios como sujetos obligados',
          autoridad: 'la UIF-Perú', portal: 'su sistema de reporte en línea' },
    AR: { ley: 'la Ley N.º 25.246 (artículo 20) y la Resolución UIF 43/2024 para agentes y corredores inmobiliarios',
          autoridad: 'la UIF', portal: 'el Sistema de Reporte de Operaciones (SRO)' },
    CL: { ley: 'la Ley N.º 19.913, que incluye a los corredores de propiedades como sujetos obligados',
          autoridad: 'la UAF', portal: 'su portal de entidades reportantes' },
  };

  function g(id) { return document.getElementById(id); }
  function texto(el, t) { if (el) el.textContent = t; }
  function ocultar(el) { if (el) el.style.display = 'none'; }
  function etiqueta(id, t) { texto(document.querySelector('label[for="' + id + '"]'), t); }
  function bloque(titulo) {
    var t = Array.prototype.find.call(document.querySelectorAll('.cp-bloque__t'),
      function (el) { return el.textContent.indexOf(titulo) !== -1; });
    return t && t.closest('.cp-bloque');
  }

  function aplicar() {
    var c = window.bkPais ? bkPais() : 'MX';
    var l = LEY[c];
    if (!l || !window.bkPaisCfg) return;
    var cfg = bkPaisCfg(c);

    // Leyenda.
    var ps = document.querySelectorAll('.cp-ley > p');
    if (ps[0]) ps[0].innerHTML = 'En ' + cfg.nombre + ' la intermediación inmobiliaria está sujeta a ' + l.ley +
      '. Eso se traduce en tres deberes: <strong>identificar</strong> a tu cliente e integrar su expediente, ' +
      '<strong>conservarlo</strong> y <strong>reportar</strong> ante ' + l.autoridad + ' las operaciones sospechosas.';
    if (ps[1]) ps[1].textContent = 'Las operaciones del mismo cliente se suman dentro de la ventana de acumulación. ' +
      'Cuando una operación rebasa tu monto de alerta o la marcas como inusual, revísala con tu oficial de ' +
      'cumplimiento y, si corresponde, repórtala en ' + l.portal + '. Los montos y plazos exactos los fija la ' +
      'norma vigente de ' + cfg.nombre + ': confírmalos y ajústalos en Ajustes.';
    ocultar(document.querySelector('.cp-ley__link'));

    if (g('cp-buscar')) g('cp-buscar').placeholder = 'Buscar por nombre o ' + cfg.idFiscal;

    // Avisos en XML: solo México.
    ocultar(document.querySelector('#cp-tabs [data-vista="avisos"]'));
    ocultar(g('v-avisos'));
    var lim = g('cp-k-lim');
    ocultar(lim && lim.closest('.cp-kpi'));
    texto(document.querySelector('.cp-kpi--aviso .cp-kpi__pie'), 'Operaciones para revisar o reportar');
    texto(document.querySelector('.cp-kpi--aviso .cp-kpi__label'), 'Por revisar');
    texto(g('cp-k-umb-pie'), 'Monto de alerta interna');
    var umb = g('cp-k-umb');
    texto(umb && umb.closest('.cp-kpi') && umb.closest('.cp-kpi').querySelector('.cp-kpi__label'), 'Monto de alerta');

    // Ajustes.
    ocultar(bloque('Tu alta ante el SAT'));
    etiqueta('cf-resp-rfc', cfg.idFiscal);
    var montos = bloque('Montos vigentes');
    if (montos) {
      texto(montos.querySelector('.cp-bloque__t'), 'Monto de alerta');
      texto(montos.querySelector('.cp-bloque__d'), 'Las operaciones que, solas o sumadas dentro de la ventana, ' +
        'lleguen a este monto se marcan para revisión. Ponlo de acuerdo con la norma vigente de ' + cfg.nombre +
        ' y tu manual de cumplimiento.');
    }
    ['cf-uma', 'cf-vig', 'cf-dia'].forEach(function (id) {
      var el = g(id);
      ocultar(el && el.closest('.bk-field'));
    });
    if (g('cf-uma')) g('cf-uma').value = 1;

    // Expediente: sin CURP; el RFC es el identificador tributario del país.
    ['e-curp', 'e-rcurp', 'e-bccurp'].forEach(function (id) {
      var el = g(id);
      ocultar(el && el.closest('.bk-field'));
    });
    ['e-rfc', 'e-rfcm', 'e-rrfc', 'e-bcrfc'].forEach(function (id) {
      etiqueta(id, cfg.idFiscal);
      if (g(id)) g(id).removeAttribute('maxlength');
    });
    var ine = document.querySelector('#e-idtipo option[value="INE"]');
    texto(ine, 'Documento de identidad (' + cfg.idPersona + ')');
    etiqueta('cf-umbral', 'Monto de alerta (' + cfg.moneda + ')');
  }

  document.addEventListener('bk:pais', aplicar);
  if (window.__BK_PAIS) aplicar();
})();
