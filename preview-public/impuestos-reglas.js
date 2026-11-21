/* ══════════════════════════════════════════════════════════════════
   Impuestos por la venta de un inmueble — reglas por país.

   Solo personas naturales/humanas residentes que venden un inmueble que
   NO es parte de un negocio. Es una estimación para orientar al cliente:
   cada resultado trae sus advertencias y el texto pide confirmar con un
   contador. México NO vive aquí: tiene su calculadora propia (isr.html).

   Los valores que cambian cada año (UVT, UIT, UF) son editables en la
   pantalla; aquí solo está el valor por defecto con su fecha.

   Lo usan impuestos.html y tests/test_impuestos_reglas.py (con node).
   ══════════════════════════════════════════════════════════════════ */
(function (raiz) {
  'use strict';

  var PARAMETROS = {
    CO: { uvt: 52374, uvtAnio: 2026, tarifa: 0.15, exentasUvt: 5000, retencion: 0.01 },
    PE: { uit: 5500, uitAnio: 2026, tasa: 0.05, alcabala: 0.03, alcabalaUitExentas: 10 },
    AR: { tasa: 0.15, desde: '2018-01-01' },
    CL: { exentoUf: 8000, tasaUnica: 0.10, desde: '2004-01-01' },
  };

  function n(v) { v = Number(v); return isFinite(v) && v > 0 ? v : 0; }
  function anios(desde, hasta) {
    if (!desde) return null;
    var a = new Date(desde), b = hasta ? new Date(hasta) : new Date();
    if (isNaN(a) || isNaN(b)) return null;
    return (b - a) / (365.25 * 24 * 3600 * 1000);
  }
  function antesDe(fecha, limite) { return !!fecha && String(fecha) < limite; }

  /* Cada regla recibe:
       venta, costo, mejoras   montos en la misma moneda
       fechaCompra, fechaVenta 'AAAA-MM-DD'
       casaHabitacion          true/false
       + campos propios del país
     y regresa { impuesto, base, lineas:[{l,v,tipo}], avisos:[...], nota } */
  var REGLAS = {

    /* Colombia — ganancia ocasional (ET arts. 299-311-1, Ley 2277 de 2022). */
    CO: function (d) {
      var p = PARAMETROS.CO, uvt = n(d.uvt) || p.uvt;
      var venta = n(d.venta), costo = n(d.costo) + n(d.mejoras);
      var utilidad = Math.max(0, venta - costo);
      var t = anios(d.fechaCompra, d.fechaVenta);
      var retencion = venta * p.retencion;
      var lineas = [
        { l: 'Precio de venta', v: venta },
        { l: 'Costo fiscal (compra + mejoras)', v: -costo },
        { l: 'Utilidad', v: utilidad, tipo: 'sub' },
      ];
      var avisos = [];
      if (t !== null && t < 2) {
        avisos.push('Tuviste el inmueble menos de 2 años: la utilidad no es ganancia ocasional, se suma a tu renta ordinaria del año y paga con la tarifa progresiva (0% a 39%). Aquí solo se muestra la utilidad.');
        lineas.push({ l: 'Retención en la fuente en notaría (1% del precio, se descuenta en tu declaración)', v: retencion });
        return { impuesto: null, base: utilidad, lineas: lineas, avisos: avisos, retencion: retencion };
      }
      var exenta = 0;
      if (d.casaHabitacion && d.reinvierte) exenta = Math.min(utilidad, p.exentasUvt * uvt);
      else if (d.casaHabitacion) avisos.push('Las primeras 5.000 UVT de la utilidad de tu casa o apartamento de habitación quedan exentas solo si el dinero de la venta se deposita en una cuenta AFC/AVC o se usa para pagar el crédito hipotecario de ese inmueble.');
      var base = utilidad - exenta;
      var impuesto = base * p.tarifa;
      if (exenta) lineas.push({ l: 'Exenta: primeras 5.000 UVT (casa de habitación)', v: -exenta });
      lineas.push({ l: 'Ganancia ocasional gravada', v: base, tipo: 'sub' });
      lineas.push({ l: 'Impuesto de ganancia ocasional (15%)', v: impuesto, tipo: 'tot' });
      lineas.push({ l: 'Retención en la fuente en notaría (1% del precio, anticipo que se descuenta)', v: retencion });
      avisos.push('El costo fiscal puede ser mayor si se reajusta (arts. 70 y 73 del Estatuto Tributario) o si se toma el avalúo catastral. Revísalo con tu contador.');
      return { impuesto: impuesto, base: base, lineas: lineas, avisos: avisos, retencion: retencion,
               nota: 'UVT ' + p.uvtAnio + ': $' + uvt.toLocaleString('es-CO') };
    },

    /* Perú — renta de segunda categoría (LIR art. 2 y 36; 5% efectivo). */
    PE: function (d) {
      var p = PARAMETROS.PE, uit = n(d.uit) || p.uit;
      var venta = n(d.venta);
      var icm = n(d.icm) || 1;
      var costo = n(d.costo) * icm + n(d.mejoras);
      var ganancia = Math.max(0, venta - costo);
      var alcabala = Math.max(0, venta - p.alcabalaUitExentas * uit) * p.alcabala;
      var lineas = [
        { l: 'Precio de venta', v: venta },
        { l: 'Costo computable (compra × índice de corrección + mejoras)', v: -costo },
        { l: 'Ganancia de capital', v: ganancia, tipo: 'sub' },
      ];
      var avisos = ['Si vendes más de dos inmuebles en el mismo año, desde la tercera venta se considera habitualidad y tributa como renta empresarial (con IGV en algunos casos).'];
      var impuesto;
      if (antesDe(d.fechaCompra, '2004-01-01')) {
        impuesto = 0;
        avisos.unshift('Comprado antes del 1 de enero de 2004: la ganancia de una persona natural no está gravada.');
      } else if (d.casaHabitacion) {
        impuesto = 0;
        avisos.unshift('La venta de tu casa habitación no paga impuesto a la renta. Debe haber sido tu vivienda y no haberse usado para un negocio; si tienes varias, solo una califica.');
      } else {
        impuesto = ganancia * p.tasa;
      }
      lineas.push({ l: 'Impuesto a la renta (5% de la ganancia)', v: impuesto, tipo: 'tot' });
      lineas.push({ l: 'Alcabala que paga el comprador (3% sobre lo que exceda 10 UIT)', v: alcabala });
      if (impuesto) avisos.push('Se paga con el Formulario Virtual 1665 antes de firmar la escritura pública; el notario pide la constancia.');
      return { impuesto: impuesto, base: ganancia, lineas: lineas, avisos: avisos, alcabala: alcabala,
               nota: 'UIT ' + p.uitAnio + ': S/ ' + uit.toLocaleString('es-PE') };
    },

    /* Argentina — impuesto cedular (Ley 27.430) e ITI derogado (Ley 27.743). */
    AR: function (d) {
      var p = PARAMETROS.AR;
      var venta = n(d.venta), costo = n(d.costo) + n(d.mejoras);
      var ganancia = Math.max(0, venta - costo);
      var lineas = [
        { l: 'Precio de venta', v: venta },
        { l: 'Costo actualizado (compra + mejoras)', v: -costo },
        { l: 'Ganancia', v: ganancia, tipo: 'sub' },
      ];
      var avisos = [];
      var impuesto;
      if (antesDe(d.fechaCompra, p.desde)) {
        impuesto = 0;
        avisos.push('Comprado antes del 1 de enero de 2018: no paga impuesto cedular, y el Impuesto a la Transferencia de Inmuebles (ITI, 1,5%) quedó derogado por la Ley 27.743 desde julio de 2024.');
      } else if (d.casaHabitacion) {
        impuesto = 0;
        avisos.push('La venta de tu casa habitación está exenta del impuesto cedular.');
      } else {
        impuesto = ganancia * p.tasa;
        avisos.push('El costo se actualiza por inflación (IPC) desde la compra; si la operación es en dólares, la ganancia se mide en pesos al tipo de cambio de cada fecha. Confírmalo con tu contador.');
      }
      lineas.push({ l: 'Impuesto cedular (15% de la ganancia)', v: impuesto, tipo: 'tot' });
      avisos.push('No incluye el impuesto de sellos de tu provincia ni honorarios de escribanía.');
      return { impuesto: impuesto, base: ganancia, lineas: lineas, avisos: avisos };
    },

    /* Chile — mayor valor en bienes raíces (LIR art. 17 N° 8 letra b). */
    CL: function (d) {
      var p = PARAMETROS.CL;
      var venta = n(d.venta), costo = n(d.costo) + n(d.mejoras);
      var mayor = Math.max(0, venta - costo);
      // Montos en UF o en pesos; el tope de 8.000 UF se pasa a la moneda del cálculo.
      var uf = n(d.valorUf);
      var enUf = d.moneda === 'UF';
      var disponibleUf = Math.max(0, p.exentoUf - n(d.ufUsadas));
      var disponible = enUf ? disponibleUf : disponibleUf * uf;
      var lineas = [
        { l: 'Precio de venta', v: venta },
        { l: 'Costo reajustado por IPC (compra + mejoras)', v: -costo },
        { l: 'Mayor valor', v: mayor, tipo: 'sub' },
      ];
      var avisos = [];
      var t = anios(d.fechaCompra, d.fechaVenta);
      if (antesDe(d.fechaCompra, p.desde)) {
        lineas.push({ l: 'Impuesto', v: 0, tipo: 'tot' });
        avisos.push('Comprado antes del 1 de enero de 2004: aplica el régimen anterior y el mayor valor suele no constituir renta. Confírmalo con tu contador.');
        return { impuesto: 0, base: mayor, lineas: lineas, avisos: avisos };
      }
      if (t !== null && t < 1) {
        avisos.push('Pasó menos de un año entre la compra y la venta: no aplica el beneficio de 8.000 UF y el mayor valor se suma a tu Global Complementario.');
        lineas.push({ l: 'Impuesto', v: null, tipo: 'tot' });
        return { impuesto: null, base: mayor, lineas: lineas, avisos: avisos };
      }
      if (!enUf && !uf) avisos.push('Escribe el valor de la UF para aplicar el tope de 8.000 UF.');
      var exento = Math.min(mayor, disponible);
      var exceso = mayor - exento;
      var impuesto = exceso * p.tasaUnica;
      lineas.push({ l: 'Ingreso no renta (tope de por vida: 8.000 UF)', v: -exento });
      lineas.push({ l: 'Exceso afecto', v: exceso, tipo: 'sub' });
      lineas.push({ l: 'Impuesto único sustitutivo (10% del exceso)', v: impuesto, tipo: 'tot' });
      avisos.push('El exceso también se puede declarar en el Global Complementario en vez del 10%; conviene si tu tasa marginal es menor. El comprador no debe ser una persona relacionada contigo.');
      avisos.push('Si es un departamento de edificio acogido a la ley de pisos o un lote de subdivisión, el plazo mínimo es de 4 años, no de 1.');
      return { impuesto: impuesto, base: exceso, lineas: lineas, avisos: avisos,
               nota: enUf ? 'Montos en UF' : (uf ? 'UF: $' + uf.toLocaleString('es-CL') : '') };
    },
  };

  function calcular(pais, datos) {
    var r = REGLAS[pais];
    if (!r) throw new Error('País sin calculadora: ' + pais);
    return r(datos || {});
  }

  var api = { PARAMETROS: PARAMETROS, calcular: calcular, paises: Object.keys(REGLAS) };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else raiz.BK_IMPUESTOS = api;
})(this);
