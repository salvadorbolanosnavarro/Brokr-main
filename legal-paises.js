/* ══════════════════════════════════════════════════════════════════
   Anexos legales por país (Colombia, Perú, Argentina y Chile).

   legal.html está redactado para México. Para una cuenta de otro país se
   antepone, arriba de cada documento, el anexo de ese país: dice qué ley
   de datos y de consumo aplica, ante qué autoridad, en qué moneda se
   cobra y qué cláusulas mexicanas se sustituyen. Lo que el anexo no
   modifica sigue igual.

   El país sale de ?pais=XX, o del de la cuenta/landing (paises.js).

   IMPORTANTE: textos preparados como base; deben revisarlos abogados de
   cada país antes de vender allá.
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var ANEXOS = {
    CO: {
      datos: 'la Ley Estatutaria 1581 de 2012 y el Decreto 1377 de 2013 (compilado en el Decreto Único 1074 de 2015)',
      autoridad: 'la Superintendencia de Industria y Comercio (SIC), Delegatura para la Protección de Datos Personales (www.sic.gov.co)',
      derechos: 'conocer, actualizar, rectificar y suprimir sus datos, solicitar prueba de la autorización y revocarla. Las consultas se atienden en un máximo de diez (10) días hábiles y los reclamos en quince (15) días hábiles, prorrogables en los términos de la ley',
      consumo: 'la Ley 1480 de 2011 (Estatuto del Consumidor), cuya autoridad es la Superintendencia de Industria y Comercio. Cuando el Usuario actúe como consumidor, conserva el derecho de retracto de cinco (5) días hábiles previsto para las ventas a distancia',
      impuesto: 'el IVA que la ley colombiana impone a los servicios digitales prestados desde el exterior',
    },
    PE: {
      datos: 'la Ley N.º 29733, Ley de Protección de Datos Personales, y su Reglamento',
      autoridad: 'la Autoridad Nacional de Protección de Datos Personales del Ministerio de Justicia y Derechos Humanos (www.gob.pe/anpd)',
      derechos: 'información, acceso, rectificación, cancelación, oposición y tratamiento objetivo de sus datos, dentro de los plazos que fija el Reglamento de la Ley N.º 29733',
      consumo: 'el Código de Protección y Defensa del Consumidor (Ley N.º 29571), cuya autoridad es el INDECOPI. El Usuario puede presentar reclamos o quejas en el correo de contacto indicado al final de este documento',
      impuesto: 'el IGV que la ley peruana impone a los servicios digitales prestados por sujetos no domiciliados',
    },
    AR: {
      datos: 'la Ley N.º 25.326 de Protección de los Datos Personales y su Decreto Reglamentario 1558/2001',
      autoridad: 'la Agencia de Acceso a la Información Pública (AAIP), órgano de control de la Ley N.º 25.326 (www.argentina.gob.ar/aaip)',
      derechos: 'acceso, rectificación, actualización y supresión de sus datos. El acceso se responde dentro de los diez (10) días corridos y la rectificación o supresión dentro de los cinco (5) días hábiles, en los términos de la ley',
      consumo: 'la Ley N.º 24.240 de Defensa del Consumidor y el Código Civil y Comercial de la Nación. Cuando el Usuario actúe como consumidor, puede revocar la contratación dentro de los diez (10) días corridos (botón de arrepentimiento) y dar de baja la Suscripción por el mismo medio en que la contrató, desde la propia Plataforma',
      impuesto: 'el IVA y las percepciones que la ley argentina aplica a los servicios digitales prestados desde el exterior y a los pagos con tarjeta en moneda extranjera',
    },
    CL: {
      datos: 'la Ley N.º 19.628 sobre Protección de la Vida Privada, con las modificaciones de la Ley N.º 21.719 a partir de su entrada en vigencia',
      autoridad: 'la Agencia de Protección de Datos Personales creada por la Ley N.º 21.719 y, mientras no entre en funciones, los tribunales competentes',
      derechos: 'acceso, rectificación, supresión, oposición, portabilidad y bloqueo de sus datos, en los plazos que fije la ley',
      consumo: 'la Ley N.º 19.496 sobre Protección de los Derechos de los Consumidores, cuya autoridad es el SERNAC. Cuando el Usuario actúe como consumidor, conserva el derecho de retracto de diez (10) días que la ley reconoce en la contratación por medios electrónicos, salvo que se haya excluido de forma expresa e inequívoca antes de contratar',
      impuesto: 'el IVA que la ley chilena impone a los servicios digitales prestados por proveedores extranjeros',
    },
  };

  function texto(panel, p, a) {
    var n = p.nombre;
    var porPanel = {
      tyc: [
        'Para los Usuarios cuya cuenta está registrada en ' + n + ', las referencias de estos Términos a la LFPDPPP, a la PROFECO, al INAI, al CFDI y a la legislación mexicana de protección al consumidor se entienden hechas, respectivamente, a ' + a.datos + ', a la autoridad de consumo de ' + n + ' y a ' + a.consumo + '.',
        'La Plataforma se presta desde México. La cláusula de legislación aplicable y jurisdicción se mantiene en lo que la ley de ' + n + ' lo permita; los derechos irrenunciables que esa ley otorga a los consumidores prevalecen sobre cualquier cláusula en contrario.',
        'Los contratos modelo y el módulo de Cumplimiento (PLD) se adaptan a la ley de ' + n + ' y son una referencia que el Usuario debe revisar con un abogado local; el Cálculo de ISR es exclusivo de México. Los cálculos de impuestos, las estimaciones de valor y demás resultados de la Plataforma son orientativos y no sustituyen la asesoría de un profesional habilitado en ' + n + '.',
      ],
      contrato: [
        'Para Suscriptores de ' + n + ', los precios se expresan y cobran en dólares de los Estados Unidos de América (USD) y sustituyen a lo dicho sobre pesos mexicanos en la cláusula 2.4. El banco emisor de la tarjeta puede aplicar su propio tipo de cambio y comisiones.',
        'El precio no incluye ' + a.impuesto + '; cuando corresponda, se agregará al cobro o será percibido por la entidad emisora del medio de pago conforme a la ley de ' + n + '.',
        'Los comprobantes fiscales se emiten conforme a la legislación de México, país desde donde se presta el servicio.',
      ],
      privacidad: [
        'Para titulares en ' + n + ', el tratamiento de datos personales se rige además por ' + a.datos + '. Las referencias a la LFPDPPP y a los derechos ARCO se entienden hechas a esa ley.',
        'El titular puede ejercer sus derechos de ' + a.derechos + ', escribiendo al correo de contacto indicado en este Aviso. Si considera que su solicitud no fue atendida, puede acudir ante ' + a.autoridad + '.',
        'Los datos se alojan en servidores fuera de ' + n + ' (principalmente en los Estados Unidos de América). Al aceptar este Aviso, el titular autoriza esa transferencia internacional, que se realiza con proveedores que ofrecen niveles adecuados de protección.',
      ],
      whatsapp: [
        'Si la cuenta del Usuario está registrada en ' + n + ', el Usuario es el responsable de los datos de las personas que escriban a su número en los términos de ' + a.datos + ', y Broquer actúa como encargado del tratamiento por cuenta del Usuario.',
        'Las obligaciones de este Anexo que remiten a la LFPDPPP (aviso de privacidad propio, atención de derechos y plazos) se cumplen conforme a la ley de ' + n + ', ante ' + a.autoridad + '.',
      ],
    };
    return porPanel[panel] || [];
  }

  function codigo() {
    var q = '';
    try { q = new URLSearchParams(location.search).get('pais') || ''; } catch (_) {}
    q = q.toUpperCase();
    if (window.BK_PAISES && BK_PAISES[q]) return q;
    return window.bkPais ? bkPais() : 'MX';
  }

  function pintar() {
    document.querySelectorAll('.bk-anexo-pais').forEach(function (el) { el.remove(); });
    var c = codigo();
    var a = ANEXOS[c];
    if (!a || !window.BK_PAISES) return;
    var p = BK_PAISES[c];
    ['tyc', 'contrato', 'privacidad', 'whatsapp'].forEach(function (panel) {
      var wrap = document.querySelector('#panel-' + panel + ' .doc-wrap');
      var fecha = wrap && wrap.querySelector('.doc-date');
      if (!wrap) return;
      var box = document.createElement('div');
      box.className = 'notice-banner bk-anexo-pais';
      var t = document.createElement('strong');
      t.textContent = 'ANEXO PARA ' + p.nombre.toUpperCase();
      box.appendChild(t);
      texto(panel, p, a).forEach(function (frase, i) {
        var par = document.createElement('p');
        par.textContent = (i + 1) + '. ' + frase;
        par.style.margin = 'var(--sp-2) 0 0';
        box.appendChild(par);
      });
      var nota = document.createElement('p');
      nota.style.margin = 'var(--sp-2) 0 0';
      nota.textContent = 'Este anexo prevalece sobre el texto que sigue en lo que se le oponga. Lo demás aplica igual.';
      box.appendChild(nota);
      if (fecha && fecha.nextSibling) wrap.insertBefore(box, fecha.nextSibling);
      else wrap.insertBefore(box, wrap.firstChild);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', pintar);
  else pintar();
  document.addEventListener('bk:pais', pintar);
})();
