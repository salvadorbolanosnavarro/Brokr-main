/* ══════════════════════════════════════════════════════════════════
   Calculadora avanzada de impuestos por la venta de un inmueble.

   Para operaciones que la calculadora simple no cubre: varios
   titulares, cada uno con su derecho (pleno dominio, nuda propiedad,
   usufructo, uso y habitación) y su cuota; cada titular con una o
   varias "adquisiciones" (tramos) en fechas, costos y formas
   distintas (compra, herencia, donación, adjudicación, consolidación
   del usufructo); residentes y no residentes; avalúo de referencia;
   gastos de venta; e impuestos del comprador.

   Cada país tiene su propio motor (MX, CO, PE, AR, CL) con sus reglas.
   El motor es puro: no consulta nada. La página (impuestos-avanzada.html)
   trae el INPC y las UDIS de México antes de llamarlo.

   Es una estimación para preparar la operación; el cálculo definitivo
   lo hace el notario/escribano. Cada resultado trae sus fundamentos y
   advertencias.

   Lo usan impuestos-avanzada.html y tests/test_impuestos_avanzada.py.
   ══════════════════════════════════════════════════════════════════ */
(function (raiz) {
  'use strict';

  /* ── Utilidades ─────────────────────────────────────────────── */
  function n(v) { v = Number(v); return isFinite(v) && v > 0 ? v : 0; }
  function r2(v) { return Math.round(v * 100) / 100; }
  function fecha(s) {
    if (!s) return null;
    var m = String(s).match(/^(\d{4})-(\d{2})(?:-(\d{2}))?/);
    if (!m) return null;
    return { a: +m[1], m: +m[2], d: m[3] ? +m[3] : 15 };
  }
  // Años cumplidos entre dos fechas (fracción incluida).
  function aniosEntre(a, b) {
    var x = fecha(a), y = fecha(b);
    if (!x || !y) return null;
    return ((y.a - x.a) * 12 + (y.m - x.m) + (y.d - x.d) / 30.4375) / 12;
  }
  function antesDe(s, limite) { return !!s && String(s) < limite; }

  /* ── Tablas de México (LISR art. 152; Anexo 8 RMF) ──────────────
     Tarifa ANUAL. La tarifa del pago provisional del art. 126 es la
     mensual del art. 96 acumulada al mes de la firma = anual × mes/12. */
  var MX_TARIFA = {
    2025: [ // 2023-2025 (sin actualización)
      [0.01, 8952.49, 0, 0.0192], [8952.50, 75984.55, 171.88, 0.0640],
      [75984.56, 133536.07, 4461.94, 0.1088], [133536.08, 155229.80, 10723.55, 0.16],
      [155229.81, 185852.57, 14194.54, 0.1792], [185852.58, 374837.88, 19682.13, 0.2136],
      [374837.89, 590795.99, 60049.40, 0.2352], [590796.00, 1127926.84, 110842.74, 0.30],
      [1127926.85, 1503902.46, 271981.99, 0.32], [1503902.47, 4511707.37, 392294.17, 0.34],
      [4511707.38, Infinity, 1417164.67, 0.35]],
    2026: [ // Anexo 8 RMF 2026 (DOF 28/12/2025)
      [0.01, 10135.11, 0, 0.0192], [10135.12, 86022.11, 194.59, 0.0640],
      [86022.12, 151176.19, 5051.37, 0.1088], [151176.20, 175735.66, 12140.13, 0.16],
      [175735.67, 210403.69, 16069.64, 0.1792], [210403.70, 424353.97, 22282.14, 0.2136],
      [424353.98, 668840.14, 67981.92, 0.2352], [668840.15, 1276925.98, 125485.07, 0.30],
      [1276925.99, 1702567.97, 307910.81, 0.32], [1702567.98, 5107703.92, 444116.23, 0.34],
      [5107703.93, Infinity, 1601862.46, 0.35]],
  };
  function mxTarifa(anio, mes) {
    var base = anio >= 2026 ? MX_TARIFA[2026] : MX_TARIFA[2025];
    var k = Math.max(1, Math.min(12, mes || 12)) / 12;
    return base.map(function (f, i) {
      return [i === 0 ? 0.01 : r2(f[0] * k), f[1] === Infinity ? Infinity : r2(f[1] * k), r2(f[2] * k), f[3]];
    });
  }
  function progresiva(tabla, base) {
    if (base <= 0) return 0;
    var fila = tabla[0];
    for (var i = 0; i < tabla.length; i++) if (base >= tabla[i][0]) fila = tabla[i];
    return fila[2] + Math.max(0, base - fila[0]) * fila[3];
  }

  /* ── Parámetros por país (valores por defecto, editables) ───── */
  var PARAMETROS = {
    MX: { exencionUdis: 700000, tasaEstatal: 0.05, iva: 0.16, noResidenteBruto: 0.25, noResidenteGanancia: 0.35, isai: 0.03 },
    CO: { uvt: 52374, uvtAnio: 2026, tarifa: 0.15, exentasUvt: 5000, retencion: 0.01,
          notariales: 0.003, registro: 0.01, derechosRegistro: 0.005 },
    PE: { uit: 5500, uitAnio: 2026, tasa: 0.05, tercera: 0.295, alcabala: 0.03, alcabalaUitExentas: 10 },
    AR: { tasa: 0.15, desde: '2018-01-01', presuncionNoResidente: 0.90, sellos: 0, escribania: 0.015 },
    CL: { exentoUf: 8000, tasaUnica: 0.10, desde: '2004-01-01', adicional: 0.35 },
  };

  /* ── Valor del usufructo según cada país ────────────────────────
     Devuelve { pct, fundamento } con pct = fracción del valor pleno que
     vale el usufructo; la nuda propiedad vale 1 − pct. */
  function chileEscala(edad) {
    // Ley 16.271 art. 6 (usufructo vitalicio por edad del usufructuario).
    var e = n(edad);
    if (e < 30) return 0.9; if (e < 40) return 0.8; if (e < 50) return 0.7; if (e < 60) return 0.6;
    if (e < 70) return 0.5; if (e < 80) return 0.4; if (e < 90) return 0.3; return 0.2;
  }
  function valorUsufructo(pais, op) {
    op = op || {};
    var metodo = op.metodo || 'pais';
    var temporal = op.tipo === 'temporal';
    if (metodo === 'manual') {
      var p = Math.min(100, Math.max(0, Number(op.pct) || 0)) / 100;
      return { pct: p, fundamento: 'Proporción pactada o de avalúo: usufructo ' + r2(p * 100) + '%' };
    }
    if (metodo === 'edad') {
      // Método de referencia (derecho comparado): 89 − edad, entre 10% y 70%;
      // temporal: 2% por año, hasta 70%.
      var q = temporal ? Math.min(0.7, 0.02 * n(op.anios)) : Math.min(0.7, Math.max(0.1, (89 - n(op.edad)) / 100));
      return { pct: q, fundamento: temporal
        ? 'Referencia comparada: 2% por año de duración (' + n(op.anios) + ' años), máximo 70%'
        : 'Referencia comparada: 89 − edad del usufructuario (' + n(op.edad) + ' años), entre 10% y 70%' };
    }
    switch (pais) {
      case 'CO':
        return temporal
          ? { pct: Math.min(0.7, 0.05 * n(op.anios)), fundamento: 'ET art. 303: usufructo temporal 5% por año (' + n(op.anios) + ' años), máximo 70%' }
          : { pct: 0.7, fundamento: 'ET art. 303: usufructo vitalicio 70%, nuda propiedad 30%' };
      case 'CL':
        if (temporal) return { pct: 0.5, fundamento: 'Sin escala para usufructo temporal: se usa 50%. Captura la proporción pactada si la hay.' };
        return { pct: chileEscala(op.edad), fundamento: 'Ley 16.271 art. 6: escala por edad del usufructuario (' + n(op.edad) + ' años)' };
      case 'MX':
        return { pct: 0.5, fundamento: 'Práctica notarial y códigos fiscales locales (p. ej. CDMX y Estado de México): usufructo y nuda propiedad valen 50% cada uno' };
      default:
        return { pct: 0.5, fundamento: 'La ley no fija una proporción para este impuesto: se usa 50%. Captura la del avalúo o la pactada en la escritura.' };
    }
  }

  var DERECHOS = {
    pleno: 'Pleno dominio', nuda: 'Nuda propiedad', usufructo: 'Usufructo', uso: 'Uso y habitación',
  };
  // Peso de cada derecho sobre el valor pleno del inmueble.
  function pesoDerecho(derecho, pctUsuf) {
    if (derecho === 'nuda') return 1 - pctUsuf;
    if (derecho === 'usufructo') return pctUsuf;
    if (derecho === 'uso') return pctUsuf * 0.75; // referencia: uso y habitación = 75% del usufructo
    return 1;
  }

  /* ── Estructura común: reparte el precio y revisa la cobertura ──
     Cada titular vende la "cuota" (%) de su derecho. Ejemplo: madre con
     usufructo 100% y dos hijos con nuda propiedad 50% cada uno. */
  function preparar(pais, e) {
    var avisos = [];
    var precio = n(e.precio);
    // Una sola valoración del usufructo para toda la operación (así nuda
    // propiedad + usufructo suman exactamente 100%). La edad, si no viene,
    // es la del primer usufructuario capturado.
    var usufOp = Object.assign({}, e.usufructo || {});
    if (!n(usufOp.edad)) {
      var uft = (e.titulares || []).filter(function (t) { return t.derecho === 'usufructo' && n(t.edad); })[0];
      if (uft) usufOp.edad = uft.edad;
    }
    var u = valorUsufructo(pais, usufOp);
    var usaDesmembrado = (e.titulares || []).some(function (t) { return t.derecho && t.derecho !== 'pleno'; });
    var titulares = (e.titulares || []).map(function (t, i) {
      var pctU = u.pct;
      var cuota = Math.min(100, n(t.cuota)) / 100;
      var peso = pesoDerecho(t.derecho || 'pleno', pctU);
      var tramos = (t.tramos && t.tramos.length ? t.tramos : [{}]).map(function (k) { return Object.assign({}, k); });
      var sumaTr = tramos.reduce(function (s, k) { return s + (n(k.pct) || 0); }, 0);
      if (!sumaTr) tramos.forEach(function (k) { k.pct = 100 / tramos.length; });
      else if (Math.abs(sumaTr - 100) > 0.01) {
        avisos.push((t.nombre || 'Titular ' + (i + 1)) + ': las adquisiciones suman ' + r2(sumaTr) + '% de su parte; se reparten en proporción.');
        tramos.forEach(function (k) { k.pct = n(k.pct) * 100 / sumaTr; });
      }
      return Object.assign({}, t, {
        nombre: t.nombre || 'Titular ' + (i + 1),
        derecho: t.derecho || 'pleno', cuota: cuota, peso: peso, pctUsufructo: pctU,
        valor: precio * peso * cuota, participacion: peso * cuota, tramos: tramos,
        residente: t.residente !== false,
      });
    });
    // Cobertura de las capas: pleno + nuda debe sumar 100% de la propiedad y
    // pleno + usufructo 100% del goce. Si no, se está vendiendo solo una parte.
    var capaProp = 0, capaGoce = 0;
    titulares.forEach(function (t) {
      if (t.derecho === 'pleno') { capaProp += t.cuota; capaGoce += t.cuota; }
      if (t.derecho === 'nuda') capaProp += t.cuota;
      if (t.derecho === 'usufructo') capaGoce += t.cuota;
    });
    if (titulares.length && Math.abs(capaProp - 1) > 0.0001)
      avisos.push('Las cuotas de propiedad (pleno dominio + nuda propiedad) suman ' + r2(capaProp * 100) + '%, no 100%: solo se calcula lo que venden los titulares capturados.');
    if (usaDesmembrado && Math.abs(capaGoce - 1) > 0.0001 && titulares.some(function (t) { return t.derecho === 'usufructo'; }))
      avisos.push('Las cuotas de goce (pleno dominio + usufructo) suman ' + r2(capaGoce * 100) + '%. Si el usufructuario conserva su usufructo (venta con reserva), el comprador adquiere solo la nuda propiedad.');
    if (titulares.some(function (t) { return t.derecho === 'uso'; }))
      avisos.push('El derecho de uso y habitación se valora en 75% del usufructo (criterio de referencia). Ajústalo con avalúo si hace falta.');
    var vendido = titulares.reduce(function (s, t) { return s + t.valor; }, 0);
    return { precio: precio, usufructo: u, usaDesmembrado: usaDesmembrado, titulares: titulares, avisos: avisos, vendido: vendido };
  }

  // Reparte un monto de la operación (comisión, gastos) según participación.
  function reparto(monto, t, prep) { return prep.vendido ? n(monto) * t.valor / prep.vendido : 0; }

  /* ════════════════════════ MÉXICO ════════════════════════════
     LISR arts. 93 fr. XIX, 119-127 y 160; LIVA art. 9. Por cada tramo:
     costo (terreno actualizado + construcción depreciada 3% anual, mín.
     20%, actualizada), piso 10% del precio, mejoras, gastos; ganancia ÷
     años (máx. 20), tarifa art. 96 acumulada al mes (art. 126), × años. */
  function MX(e, prep) {
    var p = PARAMETROS.MX;
    var fv = fecha(e.fechaVenta) || { a: new Date().getFullYear(), m: new Date().getMonth() + 1 };
    var tabla = mxTarifa(fv.a, fv.m);
    var udi = n(e.udi);
    var limite = udi * p.exencionUdis;
    var pctTerreno = e.tipo === 'terreno' ? 1 : Math.min(100, n(e.pctTerreno) || 20) / 100;
    var avisosOp = [];
    var res = prep.titulares.map(function (t) {
      var lineas = [], avisos = [], venta = t.valor;
      lineas.push({ l: DERECHOS[t.derecho] + ' ' + r2(t.cuota * 100) + '%' + (t.derecho !== 'pleno' ? ' (vale ' + r2(t.peso * 100) + '% del inmueble)' : ''), v: venta, tipo: 'sub' });
      var comision = reparto(e.comision, t, prep), notVenta = reparto(e.gastosVenta, t, prep);
      // No residente (art. 160): 25% del ingreso sin deducciones, o 35% de la
      // ganancia si tiene representante en México y hay avalúo.
      if (!t.residente) {
        var brutoNR = venta * p.noResidenteBruto;
        var gananciaNR = calcularTramosMX(t, e, venta, tabla, fv, pctTerreno, comision, notVenta, lineas, true).ganancia;
        var opcion35 = t.representante ? Math.max(0, gananciaNR) * p.noResidenteGanancia : null;
        var imp = opcion35 !== null ? Math.min(brutoNR, opcion35) : brutoNR;
        lineas.length = 1;
        lineas.push({ l: 'No residente: 25% del precio sin deducciones (art. 160 LISR)', v: brutoNR });
        if (opcion35 !== null) lineas.push({ l: 'Opción con representante en México: 35% de la ganancia', v: opcion35 });
        lineas.push({ l: 'ISR (retiene el notario)', v: imp, tipo: 'tot' });
        avisos.push('Residente en el extranjero: no aplica la exención de casa habitación. El notario retiene y entera el ISR. Si hay tratado para evitar la doble tributación, puede cambiar.');
        return { titular: t, impuesto: imp, lineas: lineas, avisos: avisos, neto: venta - imp - comision - notVenta };
      }
      var c = calcularTramosMX(t, e, venta, tabla, fv, pctTerreno, comision, notVenta, lineas, false);
      var ganancia = c.ganancia;
      lineas.push({ l: ganancia >= 0 ? 'Ganancia' : 'Pérdida', v: ganancia, tipo: 'sub' });
      var prop = 1, exento = false;
      if (ganancia > 0 && t.casaHabitacion && !t.exencionUsada) {
        if (!udi) avisos.push('Falta el valor de la UDI del día de la firma: sin él no se puede aplicar la exención de casa habitación.');
        else if (venta <= limite) { exento = true; prop = 0; }
        else prop = (venta - limite) / venta;
        if (udi) lineas.push({ l: exento
          ? 'Exención casa habitación: el precio no rebasa 700,000 UDIS (' + fmtN(limite) + ')'
          : 'Exención casa habitación sobre 700,000 UDIS del precio (' + fmtN(limite) + '): grava ' + r2(prop * 100) + '% de la ganancia', v: -(ganancia * (1 - prop)) });
        if (t.derecho === 'nuda') avisos.push('La exención de casa habitación exige que el vendedor viva ahí. Siendo nudo propietario, normalmente quien habita es el usufructuario: confírmalo con el notario.');
      } else if (t.casaHabitacion && t.exencionUsada) {
        avisos.push('Ya usó la exención de casa habitación en los últimos 3 años: no aplica (art. 93 fr. XIX).');
      }
      var isr = 0, base = Math.max(0, ganancia) * prop;
      if (base > 0) {
        // Cada tramo se calcula con sus propios años; las pérdidas de un tramo
        // compensan a los demás en proporción.
        var positivos = c.tramos.reduce(function (s, k) { return s + Math.max(0, k.ganancia); }, 0);
        c.tramos.forEach(function (k) {
          if (k.ganancia <= 0) return;
          var bk = base * k.ganancia / positivos;
          var anual = bk / k.anios;
          var imp = progresiva(tabla, anual) * k.anios;
          isr += imp;
          lineas.push({ l: 'ISR tramo ' + k.etiqueta + ': ' + fmtN(bk) + ' ÷ ' + k.anios + ' años, tarifa acumulada a mes ' + fv.m + ' (art. 126) × ' + k.anios, v: imp });
        });
      }
      var estatal = base > 0 ? Math.min(base * p.tasaEstatal, isr) : 0;
      lineas.push({ l: 'ISR total (pago provisional que retiene el notario)', v: isr, tipo: 'tot' });
      if (isr) {
        lineas.push({ l: 'De ese total: entidad federativa 5% de la ganancia (art. 127)', v: estatal });
        lineas.push({ l: 'De ese total: federación', v: isr - estatal });
      }
      var iva = 0;
      if (e.tipo === 'comercial') {
        iva = venta * (1 - pctTerreno) * p.iva;
        lineas.push({ l: 'IVA 16% sobre la construcción (art. 9 LIVA) — lo paga el comprador además del precio', v: iva });
      }
      if (exento) avisos.push('Exento: el notario pedirá comprobantes de que es su casa habitación (INE y recibos a su nombre con ese domicilio).');
      if (ganancia < 0) avisos.push('Pérdida: puede disminuirla en su declaración anual con las reglas del art. 122 LISR.');
      avisos.push('El pago provisional se acredita en la declaración anual (art. 120): ahí la ganancia se suma a sus demás ingresos y puede resultar saldo a favor o a cargo.');
      return { titular: t, impuesto: isr, estatal: estatal, iva: iva, base: base, lineas: lineas, avisos: avisos.concat(c.avisos),
               neto: venta - isr - comision - notVenta };
    });
    // Comprador
    var baseIsai = Math.max(prep.vendido, n(e.avaluo) * (prep.vendido / (prep.precio || 1)));
    var isai = baseIsai * (e.tasaIsai !== undefined && e.tasaIsai !== '' ? Number(e.tasaIsai) / 100 : p.isai);
    var comprador = [{ l: 'ISAI (impuesto sobre adquisición de inmuebles, tasa local ' + r2((e.tasaIsai !== undefined && e.tasaIsai !== '' ? Number(e.tasaIsai) : p.isai * 100)) + '%)', v: isai }];
    if (n(e.avaluo) && n(e.avaluo) > prep.precio * 1.10)
      avisosOp.push('El avalúo rebasa el precio en más de 10%: la diferencia se considera ingreso del comprador por adquisición de bienes (arts. 130 fr. III y 131 LISR).');
    if (prep.titulares.some(function (t) { return t.derecho === 'usufructo'; }))
      avisosOp.push('En la mayoría de los códigos fiscales locales la extinción del usufructo por muerte del usufructuario no causa ISAI; su venta o renuncia onerosa sí.');
    return { titulares: res, comprador: comprador, avisos: avisosOp };
  }

  function fmtN(v) { return Math.round(v).toLocaleString('es-MX'); }

  function calcularTramosMX(t, e, venta, tabla, fv, pctTerreno, comision, notVenta, lineas, silencioso) {
    var avisos = [], tramos = [], ganancia = 0;
    t.tramos.forEach(function (k, i) {
      var frac = n(k.pct) / 100;
      var vk = venta * frac;
      var fa = fecha(k.fecha);
      var meses = fa ? (fv.a - fa.a) * 12 + (fv.m - fa.m) : 12;
      var anios = Math.max(1, Math.min(20, Math.floor(meses / 12)));
      var aniosDep = Math.max(1, Math.floor(meses / 12));
      var dep = Math.min(0.8, aniosDep * 0.03);
      var factor = n(k.factor) || 1;
      var costo = n(k.costo);
      if (k.viejosPesos) costo = costo / 1000;
      var cT = costo * pctTerreno * factor;
      var cC = costo * (1 - pctTerreno) * (1 - dep) * factor;
      var costoAct = cT + cC;
      var piso = vk * 0.10;
      var costoFinal = Math.max(costoAct, piso);
      var mej = n(k.mejoras) * (1 - dep) * factor;
      var gAdq = n(k.gastosAdq) * factor;
      var com = comision * frac, gv = notVenta * frac;
      var gk = vk - costoFinal - mej - gAdq - com - gv;
      var et = (i + 1) + (k.fecha ? ' (' + String(k.fecha).slice(0, 7) + ')' : '');
      if (!silencioso) {
        lineas.push({ l: 'Tramo ' + et + ' · ' + formaTxt(k.forma) + ' · ' + r2(n(k.pct)) + '% de su parte · factor ' + factor.toFixed(4), v: null, tipo: 'nota' });
        lineas.push({ l: '  Costo actualizado (terreno + construcción depreciada ' + Math.round(dep * 100) + '%)' + (costoFinal > costoAct ? ' → piso 10% del precio (art. 124)' : ''), v: -costoFinal });
        if (mej) lineas.push({ l: '  Mejoras depreciadas y actualizadas', v: -mej });
        if (gAdq) lineas.push({ l: '  Gastos notariales, ISAI y derechos de la adquisición, actualizados (art. 121 fr. III)', v: -gAdq });
        if (com + gv) lineas.push({ l: '  Comisión y gastos de esta venta (art. 121 fr. IV)', v: -(com + gv) });
      }
      if (!fa) avisos.push('Tramo ' + (i + 1) + ': falta la fecha de adquisición; se asumió 1 año.');
      if (!n(k.factor)) avisos.push('Tramo ' + (i + 1) + ': sin factor de actualización (INPC); el costo no se actualizó.');
      if (fa && fa.a < 1993 && !k.viejosPesos) avisos.push('Tramo ' + (i + 1) + ': adquirido antes de 1993. Si la escritura está en viejos pesos, marca la casilla para dividir el costo entre 1,000.');
      if (k.forma === 'herencia' || k.forma === 'donacion') avisos.push('Tramo ' + (i + 1) + ': en ' + formaTxt(k.forma).toLowerCase() + ' el costo y la fecha son los de quien lo adquirió de forma onerosa (autor de la sucesión o donante), art. 124 LISR.');
      if (k.forma === 'consolidacion') avisos.push('Tramo ' + (i + 1) + ': consolidación del usufructo. Lo más común es tomar el costo y la fecha de quien constituyó el usufructo; confírmalo con el notario.');
      if (k.forma === 'adjudicacion') avisos.push('Tramo ' + (i + 1) + ': adjudicación por liquidación de sociedad conyugal o copropiedad: conserva costo y fecha originales en la parte que ya le correspondía.');
      ganancia += gk;
      tramos.push({ ganancia: gk, anios: anios, etiqueta: et });
    });
    return { ganancia: ganancia, tramos: tramos, avisos: avisos };
  }

  function formaTxt(f) {
    return { compra: 'Compra', herencia: 'Herencia', donacion: 'Donación', adjudicacion: 'Adjudicación',
             consolidacion: 'Consolidación de usufructo', construccion: 'Construcción propia' }[f || 'compra'] || 'Compra';
  }

  /* Motor genérico por tramo para CO, PE, AR, CL: ganancia = venta − costo×factor − mejoras − gastos. */
  function tramosSimples(t, venta, e, prep, opts) {
    var res = [], com = opts.deduceVenta ? reparto(e.comision, t, prep) + reparto(e.gastosVenta, t, prep) : 0;
    t.tramos.forEach(function (k, i) {
      var frac = n(k.pct) / 100;
      var vk = venta * frac;
      var factor = n(k.factor) || 1;
      var costo = n(k.costo) * factor + n(k.mejoras) * (opts.mejorasConFactor ? factor : 1) + n(k.gastosAdq) * (opts.gastosAdq ? 1 : 0);
      var g = vk - costo - com * frac;
      res.push({ i: i, k: k, venta: vk, costo: costo, gastoVenta: com * frac, ganancia: g, anios: aniosEntre(k.fecha, e.fechaVenta),
                 etiqueta: (i + 1) + (k.fecha ? ' (' + String(k.fecha).slice(0, 7) + ')' : '') + ' · ' + formaTxt(k.forma) });
    });
    return res;
  }
  function lineasTramo(lineas, tr, etiquetaCosto) {
    lineas.push({ l: 'Tramo ' + tr.etiqueta + ' · ' + r2(n(tr.k.pct)) + '% de su parte', v: tr.venta });
    lineas.push({ l: '  ' + etiquetaCosto + (n(tr.k.factor) && n(tr.k.factor) !== 1 ? ' (factor ' + n(tr.k.factor) + ')' : ''), v: -tr.costo });
    if (tr.gastoVenta) lineas.push({ l: '  Comisión y gastos de esta venta', v: -tr.gastoVenta });
  }

  /* ════════════════════════ COLOMBIA ══════════════════════════
     Ganancia ocasional (ET arts. 299-311-1): 15% si se tuvo 2 años o más;
     5.000 UVT exentas de la casa de habitación si va a AFC/AVC o al
     crédito hipotecario; valor no menor al avalúo catastral (art. 90);
     retención 1% (art. 398); usufructo valuado por art. 303. */
  function CO(e, prep) {
    var p = PARAMETROS.CO, uvt = n(e.uvt) || p.uvt;
    var avaluoTotal = n(e.avaluo);
    var res = prep.titulares.map(function (t) {
      var lineas = [], avisos = [];
      var venta = t.valor;
      var minAv = avaluoTotal * t.participacion;
      if (minAv > venta) { avisos.push('Su parte del precio es menor a su parte del avalúo catastral: se declara por el avalúo (art. 90 ET).'); venta = minAv; }
      lineas.push({ l: DERECHOS[t.derecho] + ' ' + r2(t.cuota * 100) + '%' + (t.derecho !== 'pleno' ? ' (art. 303 ET: ' + r2(t.peso * 100) + '% del valor)' : ''), v: venta, tipo: 'sub' });
      var trs = tramosSimples(t, venta, e, prep, { deduceVenta: !!e.deducirGastosVenta, mejorasConFactor: false, gastosAdq: true });
      var go = 0, ordinaria = 0;
      trs.forEach(function (tr) {
        lineasTramo(lineas, tr, 'Costo fiscal (compra × reajuste + mejoras + gastos)');
        if (tr.anios !== null && tr.anios < 2) { ordinaria += Math.max(0, tr.ganancia); lineas.push({ l: '  Menos de 2 años: renta ordinaria, no ganancia ocasional', v: tr.ganancia }); }
        else go += tr.ganancia;
        if (tr.anios === null) avisos.push('Tramo ' + (tr.i + 1) + ': sin fecha; se trató como ganancia ocasional (2 años o más).');
        if (tr.k.forma === 'herencia') avisos.push('Tramo ' + (tr.i + 1) + ': por herencia el costo fiscal es el valor con que se adjudicó en la sucesión.');
      });
      go = Math.max(0, go);
      lineas.push({ l: 'Utilidad (ganancia ocasional)', v: go, tipo: 'sub' });
      var exenta = 0;
      if (t.casaHabitacion && t.reinvierte && t.residente) {
        exenta = Math.min(go, p.exentasUvt * uvt);
        lineas.push({ l: 'Exenta: primeras 5.000 UVT de la casa de habitación (art. 311-1)', v: -exenta });
      } else if (t.casaHabitacion) {
        avisos.push('La exención de 5.000 UVT exige depositar el dinero en una cuenta AFC/AVC o pagar el crédito hipotecario de esa vivienda.');
      }
      var base = go - exenta, imp = base * p.tarifa;
      lineas.push({ l: 'Ganancia ocasional gravada', v: base, tipo: 'sub' });
      lineas.push({ l: 'Impuesto de ganancia ocasional (15%)', v: imp, tipo: 'tot' });
      var impOrd = null;
      if (ordinaria > 0) {
        if (t.tasaMarginal !== undefined && t.tasaMarginal !== '' && t.tasaMarginal !== null) {
          impOrd = ordinaria * Number(t.tasaMarginal) / 100;
          lineas.push({ l: 'Renta ordinaria estimada con su tasa marginal (' + Number(t.tasaMarginal) + '%)', v: impOrd });
        } else avisos.push('Parte de la utilidad (' + Math.round(ordinaria).toLocaleString('es-CO') + ') es renta ordinaria: paga con la tarifa progresiva del art. 241 (0% a 39%). Captura su tasa marginal para estimarla.');
      }
      var ret = venta * p.retencion;
      lineas.push({ l: 'Retención en la fuente en notaría (1% del valor, anticipo)', v: ret });
      if (!t.residente) avisos.push('No residente: paga ganancia ocasional al 15% igual; la retención del 1% la practica el notario. Revisa si hay convenio de doble imposición.');
      var total = imp + (impOrd || 0);
      return { titular: t, impuesto: total, retencion: ret, lineas: lineas, avisos: avisos,
               neto: t.valor - total - reparto(e.comision, t, prep) - reparto(e.gastosVenta, t, prep) };
    });
    var baseOp = Math.max(prep.vendido, avaluoTotal * (prep.vendido / (prep.precio || 1)));
    var r = function (k) { return e[k] !== undefined && e[k] !== '' ? Number(e[k]) / 100 : PARAMETROS.CO[k]; };
    var comprador = [
      { l: 'Derechos notariales (≈' + r2(r('notariales') * 100) + '%, normalmente por mitades) + IVA 19%', v: baseOp * r('notariales') * 1.19 },
      { l: 'Impuesto de registro / beneficencia (≈' + r2(r('registro') * 100) + '%, departamental)', v: baseOp * r('registro') },
      { l: 'Derechos de registro (≈' + r2(r('derechosRegistro') * 100) + '%)', v: baseOp * r('derechosRegistro') },
    ];
    return { titulares: res, comprador: comprador,
             avisos: ['UVT ' + p.uvtAnio + ': $' + uvt.toLocaleString('es-CO') + '. Las tarifas de notaría y registro varían por departamento: ajústalas.'] };
  }

  /* ════════════════════════ PERÚ ═════════════════════════════
     Renta de 2.ª categoría (LIR art. 2, 36; Reglamento 1-A): 5% de la
     ganancia; inafecta si se adquirió antes de 2004 o es casa habitación
     con 2 años de propiedad; habitualidad (3.ª venta del año) = 3.ª
     categoría; alcabala 3% sobre lo que exceda 10 UIT (comprador). */
  function PE(e, prep) {
    var p = PARAMETROS.PE, uit = n(e.uit) || p.uit;
    var res = prep.titulares.map(function (t) {
      var lineas = [], avisos = [];
      var venta = t.valor;
      lineas.push({ l: DERECHOS[t.derecho] + ' ' + r2(t.cuota * 100) + '%' + (t.derecho !== 'pleno' ? ' (' + r2(t.peso * 100) + '% del valor)' : ''), v: venta, tipo: 'sub' });
      var trs = tramosSimples(t, venta, e, prep, { deduceVenta: false, mejorasConFactor: false, gastosAdq: true });
      var masAntiguo = trs.reduce(function (m, tr) { return tr.anios !== null && tr.anios > m ? tr.anios : m; }, -1);
      var casa = t.casaHabitacion && masAntiguo >= 2 && !t.otrosInmuebles;
      var gravada = 0;
      trs.forEach(function (tr) {
        lineasTramo(lineas, tr, 'Costo computable (compra × ICM + mejoras + gastos)');
        if (antesDe(tr.k.fecha, '2004-01-01')) lineas.push({ l: '  Adquirido antes de 2004: no gravado', v: 0 });
        else gravada += tr.ganancia;
        if (tr.k.forma === 'herencia' || tr.k.forma === 'donacion') avisos.push('Tramo ' + (tr.i + 1) + ': adquisición gratuita. El costo computable es cero, salvo que se acredite el del transferente (LIR art. 21.1). Confírmalo con SUNAT o tu contador.');
      });
      gravada = Math.max(0, gravada);
      var imp, etiqueta;
      if (t.habitual) {
        imp = gravada * p.tercera; etiqueta = 'Habitualidad: renta de 3.ª categoría (29,5%)';
        avisos.push('Desde la tercera venta del año hay habitualidad: renta empresarial y, si es primera venta de un inmueble construido por el vendedor, IGV.');
      } else if (casa && t.residente) {
        imp = 0; etiqueta = 'Casa habitación con 2 años o más: inafecta';
      } else {
        imp = gravada * p.tasa; etiqueta = 'Impuesto a la renta (5% de la ganancia)';
        if (t.casaHabitacion && masAntiguo < 2) avisos.push('Para que la casa habitación quede inafecta debe haberla tenido al menos 2 años.');
        if (t.casaHabitacion && t.otrosInmuebles) avisos.push('Tiene otros inmuebles: solo califica como casa habitación el que queda como único tras vender los demás (si se venden juntos, el de menor valor).');
      }
      lineas.push({ l: 'Ganancia gravada', v: gravada, tipo: 'sub' });
      lineas.push({ l: etiqueta, v: imp, tipo: 'tot' });
      if (imp && !t.habitual) avisos.push('Se paga con el Formulario Virtual 1665 antes de firmar la escritura; el notario pide la constancia.');
      if (!t.residente) avisos.push('No domiciliado: tasa de 5% sobre la ganancia; el comprador o el notario verifican el pago. Revisa convenios (CAN, Chile, Brasil, etc.).');
      return { titular: t, impuesto: imp, lineas: lineas, avisos: avisos, neto: t.valor - imp - reparto(e.comision, t, prep) - reparto(e.gastosVenta, t, prep) };
    });
    var baseAlc = Math.max(prep.vendido, n(e.avaluo) * (prep.vendido / (prep.precio || 1)));
    var alc = Math.max(0, baseAlc - p.alcabalaUitExentas * uit) * p.alcabala;
    return { titulares: res,
             comprador: [{ l: 'Alcabala (3% sobre lo que exceda 10 UIT; base no menor al autoavalúo)', v: alc }],
             avisos: ['UIT ' + p.uitAnio + ': S/ ' + uit.toLocaleString('es-PE') + '. La primera venta de inmuebles por la constructora no paga alcabala (paga IGV).'] };
  }

  /* ════════════════════════ ARGENTINA ═════════════════════════
     Impuesto cedular 15% (Ley 27.430) para inmuebles adquiridos desde
     2018; casa-habitación exenta; ITI derogado (Ley 27.743). No
     residentes: 15% de la ganancia real o de la presunta (90% del precio). */
  function AR(e, prep) {
    var p = PARAMETROS.AR;
    var res = prep.titulares.map(function (t) {
      var lineas = [], avisos = [];
      var venta = t.valor;
      lineas.push({ l: DERECHOS[t.derecho] + ' ' + r2(t.cuota * 100) + '%' + (t.derecho !== 'pleno' ? ' (' + r2(t.peso * 100) + '% del valor)' : ''), v: venta, tipo: 'sub' });
      var trs = tramosSimples(t, venta, e, prep, { deduceVenta: true, mejorasConFactor: true, gastosAdq: true });
      var gravada = 0;
      trs.forEach(function (tr) {
        lineasTramo(lineas, tr, 'Costo actualizado por IPC (compra + mejoras) + gastos');
        if (antesDe(tr.k.fecha, p.desde)) lineas.push({ l: '  Adquirido antes de 2018: fuera del impuesto cedular', v: 0 });
        else gravada += tr.ganancia;
      });
      gravada = Math.max(0, gravada);
      var imp;
      if (!t.residente) {
        var real = gravada * p.tasa, presunta = venta * p.presuncionNoResidente * p.tasa;
        imp = Math.min(real, presunta);
        lineas.push({ l: 'Beneficiario del exterior: 15% de la ganancia real', v: real });
        lineas.push({ l: 'o 15% de la ganancia presunta (90% del precio) = 13,5%', v: presunta });
        avisos.push('No residente: el comprador actúa como agente de retención. Se toma la opción menor; la real requiere documentar el costo.');
      } else if (t.casaHabitacion) {
        imp = 0; avisos.push('Casa-habitación: exenta del impuesto cedular.');
      } else imp = gravada * p.tasa;
      lineas.push({ l: 'Ganancia gravada', v: gravada, tipo: 'sub' });
      lineas.push({ l: t.residente ? 'Impuesto cedular (15%)' : 'Impuesto (beneficiario del exterior)', v: imp, tipo: 'tot' });
      if (e.moneda === 'USD') avisos.push('La ganancia se mide en pesos: el costo se convierte al tipo de cambio de la compra y se actualiza por IPC; el precio, al de la venta.');
      return { titular: t, impuesto: imp, lineas: lineas, avisos: avisos, neto: t.valor - imp - reparto(e.comision, t, prep) - reparto(e.gastosVenta, t, prep) };
    });
    var r = function (k) { return e[k] !== undefined && e[k] !== '' ? Number(e[k]) / 100 : PARAMETROS.AR[k]; };
    return { titulares: res,
             comprador: [
               { l: 'Impuesto de sellos provincial (' + r2(r('sellos') * 100) + '%; muchas provincias eximen la vivienda única)', v: prep.vendido * r('sellos') },
               { l: 'Honorarios de escribanía (≈' + r2(r('escribania') * 100) + '% + IVA)', v: prep.vendido * r('escribania') * 1.21 },
             ],
             avisos: ['El ITI (1,5%) quedó derogado por la Ley 27.743 desde julio de 2024.'] };
  }

  /* ════════════════════════ CHILE ═════════════════════════════
     Mayor valor (LIR art. 17 N° 8 letra b): ingreso no renta hasta
     8.000 UF de por vida por persona; exceso al 10% único o al Global
     Complementario; plazo mínimo 1 año (4 en subdivisiones y ley de
     pisos); adquiridos antes de 2004 sin tope. Usufructo por Ley 16.271. */
  function CL(e, prep) {
    var p = PARAMETROS.CL;
    var enUf = e.moneda === 'UF';
    var uf = enUf ? 1 : n(e.valorUf);
    var res = prep.titulares.map(function (t) {
      var lineas = [], avisos = [];
      var venta = t.valor;
      lineas.push({ l: DERECHOS[t.derecho] + ' ' + r2(t.cuota * 100) + '%' + (t.derecho !== 'pleno' ? ' (' + r2(t.peso * 100) + '% del valor)' : ''), v: venta, tipo: 'sub' });
      var trs = tramosSimples(t, venta, e, prep, { deduceVenta: false, mejorasConFactor: true, gastosAdq: false });
      var plazo = e.subdivision ? 4 : 1;
      var conBeneficio = 0, sinPlazo = 0, antiguo = 0;
      trs.forEach(function (tr) {
        lineasTramo(lineas, tr, 'Costo tributario reajustado por IPC (compra + mejoras en el avalúo fiscal)');
        if (antesDe(tr.k.fecha, p.desde) && (tr.anios === null || tr.anios >= 1)) { antiguo += tr.ganancia; lineas.push({ l: '  Adquirido antes de 2004: ingreso no renta, sin tope', v: 0 }); }
        else if (tr.anios !== null && tr.anios < plazo) sinPlazo += tr.ganancia;
        else conBeneficio += tr.ganancia;
      });
      conBeneficio = Math.max(0, conBeneficio); sinPlazo = Math.max(0, sinPlazo);
      if (t.relacionado) { sinPlazo += conBeneficio; conBeneficio = 0; avisos.push('Venta a una persona relacionada: no aplica el tratamiento de ingreso no renta ni el 10% único.'); }
      var imp = 0, pendiente = false;
      if (!t.residente) {
        var mayor = conBeneficio + sinPlazo;
        imp = mayor * p.adicional;
        lineas.push({ l: 'Mayor valor', v: mayor, tipo: 'sub' });
        lineas.push({ l: 'Impuesto Adicional (35%)', v: imp, tipo: 'tot' });
        avisos.push('Sin domicilio ni residencia en Chile: se estima con Impuesto Adicional 35%. Revisa si procede el 10% único y si hay convenio de doble tributación.');
        return { titular: t, impuesto: imp, lineas: lineas, avisos: avisos, neto: t.valor - imp - reparto(e.comision, t, prep) - reparto(e.gastosVenta, t, prep) };
      }
      var exento = 0, exceso = conBeneficio;
      if (conBeneficio > 0) {
        if (!uf) { pendiente = true; avisos.push('Escribe el valor de la UF para aplicar el tope de 8.000 UF.'); }
        else {
          var disp = Math.max(0, p.exentoUf - n(t.ufUsadas)) * uf;
          exento = Math.min(conBeneficio, disp); exceso = conBeneficio - exento;
          lineas.push({ l: 'Ingreso no renta (tope 8.000 UF de por vida' + (n(t.ufUsadas) ? ', ya usó ' + n(t.ufUsadas) + ' UF' : '') + ')', v: -exento });
        }
      }
      var unico = exceso * p.tasaUnica;
      lineas.push({ l: 'Exceso afecto', v: exceso, tipo: 'sub' });
      var tm = (t.tasaMarginal !== undefined && t.tasaMarginal !== '' && t.tasaMarginal !== null) ? Number(t.tasaMarginal) / 100 : null;
      if (tm !== null && exceso > 0 && exceso * tm < unico) {
        imp = exceso * tm; lineas.push({ l: 'Global Complementario a su tasa marginal (' + r2(tm * 100) + '%) — conviene más que el 10%', v: imp });
      } else {
        imp = unico; if (exceso > 0) lineas.push({ l: 'Impuesto único sustitutivo (10% del exceso)', v: unico });
      }
      if (sinPlazo > 0) {
        if (tm !== null) { imp += sinPlazo * tm; lineas.push({ l: 'Menos de ' + plazo + ' año(s): mayor valor al Global Complementario (' + r2(tm * 100) + '%)', v: sinPlazo * tm }); }
        else { pendiente = true; avisos.push('Parte del mayor valor (' + Math.round(sinPlazo).toLocaleString('es-CL') + ') no cumple el plazo de ' + plazo + ' año(s): va al Global Complementario. Captura la tasa marginal para estimarlo.'); }
      }
      lineas.push({ l: 'Impuesto', v: pendiente ? null : imp, tipo: 'tot' });
      return { titular: t, impuesto: pendiente ? null : imp, lineas: lineas, avisos: avisos,
               neto: pendiente ? null : t.valor - imp - reparto(e.comision, t, prep) - reparto(e.gastosVenta, t, prep) };
    });
    return { titulares: res, comprador: [],
             avisos: ['La compraventa entre personas naturales no paga IVA ni impuesto de timbres; el comprador paga notaría y Conservador de Bienes Raíces.'] };
  }

  var MOTORES = { MX: MX, CO: CO, PE: PE, AR: AR, CL: CL };

  function calcular(pais, escenario) {
    var motor = MOTORES[pais];
    if (!motor) throw new Error('País sin calculadora avanzada: ' + pais);
    var e = escenario || {};
    var prep = preparar(pais, e);
    var r = motor(e, prep);
    var total = 0, pendiente = false;
    r.titulares.forEach(function (x) { if (x.impuesto === null) pendiente = true; else total += x.impuesto; });
    var totalComprador = (r.comprador || []).reduce(function (s, l) { return s + (l.v || 0); }, 0);
    return {
      pais: pais, precio: prep.precio, vendido: prep.vendido,
      usufructo: prep.usaDesmembrado ? prep.usufructo : null,
      titulares: r.titulares, comprador: r.comprador || [],
      totalVendedores: pendiente ? null : total, totalParcial: total, totalComprador: totalComprador,
      avisos: prep.avisos.concat(r.avisos || []),
    };
  }

  var api = { PARAMETROS: PARAMETROS, calcular: calcular, valorUsufructo: valorUsufructo, mxTarifa: mxTarifa,
              progresiva: progresiva, DERECHOS: DERECHOS, paises: Object.keys(MOTORES) };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else raiz.BK_IMP_AVANZADA = api;
})(this);
