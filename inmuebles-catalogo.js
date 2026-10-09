// ─────────────────────────────────────────────────────────────────────────
// inmuebles-catalogo.js · Catálogo único de inmuebles (tipos, operaciones,
// características) + helpers de presentación.
//
// ARCHIVO GENERADO: no lo edites a mano. La fuente es
// core/catalogo_inmuebles.py; regenera con
//   python scripts/gen_catalogo_inmuebles.py
// (la plantilla de helpers vive en scripts/inmuebles-catalogo.plantilla.js).
//
// Lo usan: propiedades.html, propiedades-ficha.js, bolsa.html, buscador.html,
// ficha-manual.html, sitio-engine.js.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var CAT = /*__CATALOGO_INICIO__*/{
 "tipos": [
  {
   "grupo": "Residencial",
   "items": [
    {
     "key": "casa",
     "label": "Casa",
     "familia": "casa"
    },
    {
     "key": "casa_condominio",
     "label": "Casa en condominio",
     "familia": "casa"
    },
    {
     "key": "departamento",
     "label": "Departamento",
     "familia": "departamento"
    },
    {
     "key": "habitacion",
     "label": "Habitación",
     "familia": "departamento"
    },
    {
     "key": "quinta",
     "label": "Quinta",
     "familia": "casa"
    },
    {
     "key": "rancho",
     "label": "Rancho",
     "familia": "terreno"
    },
    {
     "key": "terreno",
     "label": "Terreno",
     "familia": "terreno"
    },
    {
     "key": "villa",
     "label": "Villa",
     "familia": "casa"
    }
   ]
  },
  {
   "grupo": "Comercial",
   "items": [
    {
     "key": "bodega",
     "label": "Bodega comercial",
     "familia": "bodega"
    },
    {
     "key": "casa_uso_suelo",
     "label": "Casa con uso de suelo",
     "familia": "casa"
    },
    {
     "key": "edificio",
     "label": "Edificio",
     "familia": "oficina"
    },
    {
     "key": "huerta",
     "label": "Huerta",
     "familia": "terreno"
    },
    {
     "key": "local",
     "label": "Local comercial",
     "familia": "local"
    },
    {
     "key": "local_centro_comercial",
     "label": "Local en centro comercial",
     "familia": "local"
    },
    {
     "key": "oficina",
     "label": "Oficina",
     "familia": "oficina"
    },
    {
     "key": "terreno_comercial",
     "label": "Terreno comercial",
     "familia": "terreno"
    }
   ]
  },
  {
   "grupo": "Industrial",
   "items": [
    {
     "key": "bodega_industrial",
     "label": "Bodega industrial",
     "familia": "bodega"
    },
    {
     "key": "nave_industrial",
     "label": "Nave industrial",
     "familia": "bodega"
    },
    {
     "key": "terreno_industrial",
     "label": "Terreno industrial",
     "familia": "terreno"
    }
   ]
  },
  {
   "grupo": "Otro",
   "items": [
    {
     "key": "otro",
     "label": "Otro",
     "familia": "otro"
    }
   ]
  }
 ],
 "operaciones": [
  {
   "key": "venta",
   "label": "Venta",
   "legacy": "venta"
  },
  {
   "key": "renta",
   "label": "Renta mensual",
   "legacy": "renta"
  },
  {
   "key": "preventa",
   "label": "Preventa",
   "legacy": "venta"
  },
  {
   "key": "renta_temporal",
   "label": "Renta temporal",
   "legacy": "renta"
  },
  {
   "key": "remate",
   "label": "Remate / adjudicada",
   "legacy": "venta"
  }
 ],
 "periodos": [
  {
   "key": "noche",
   "label": "por noche"
  },
  {
   "key": "semana",
   "label": "por semana"
  },
  {
   "key": "mes",
   "label": "por mes"
  }
 ],
 "unidades": [
  {
   "key": "total",
   "label": "Total"
  },
  {
   "key": "m2",
   "label": "por m²"
  },
  {
   "key": "ha",
   "label": "por hectárea"
  }
 ],
 "condiciones": [
  {
   "key": "nuevo",
   "label": "Nuevo / a estrenar"
  },
  {
   "key": "excelente",
   "label": "Excelente"
  },
  {
   "key": "bueno",
   "label": "Bueno"
  },
  {
   "key": "regular",
   "label": "Regular"
  },
  {
   "key": "remodelar",
   "label": "Para remodelar"
  },
  {
   "key": "en_construccion",
   "label": "En construcción"
  }
 ],
 "disposiciones": [
  {
   "key": "frente",
   "label": "Frente"
  },
  {
   "key": "contrafrente",
   "label": "Contrafrente"
  },
  {
   "key": "interior",
   "label": "Interior"
  },
  {
   "key": "lateral",
   "label": "Lateral"
  }
 ],
 "orientaciones": [
  {
   "key": "norte",
   "label": "Norte"
  },
  {
   "key": "sur",
   "label": "Sur"
  },
  {
   "key": "oriente",
   "label": "Oriente"
  },
  {
   "key": "poniente",
   "label": "Poniente"
  },
  {
   "key": "noreste",
   "label": "Noreste"
  },
  {
   "key": "noroeste",
   "label": "Noroeste"
  },
  {
   "key": "sureste",
   "label": "Sureste"
  },
  {
   "key": "suroeste",
   "label": "Suroeste"
  }
 ],
 "caracteristicas": [
  {
   "grupo": "Amenidades",
   "items": [
    {
     "key": "estacionamiento_visitas",
     "label": "Estacionamiento de visitas"
    },
    {
     "key": "area_comun",
     "label": "Áreas comunes",
     "alias": [
      "Área común",
      "Areas verdes",
      "Áreas verdes"
     ]
    },
    {
     "key": "asador",
     "label": "Asador",
     "alias": [
      "Área de asador",
      "BBQ"
     ]
    },
    {
     "key": "business_center",
     "label": "Business center",
     "alias": [
      "Centro de negocios"
     ]
    },
    {
     "key": "casa_club",
     "label": "Casa club",
     "alias": [
      "Club house"
     ]
    },
    {
     "key": "lavanderia",
     "label": "Lavandería",
     "alias": [
      "Cuarto de lavado",
      "Área de lavado"
     ]
    },
    {
     "key": "acceso_controlado",
     "label": "Acceso controlado",
     "alias": [
      "Caseta de vigilancia",
      "Control de acceso"
     ]
    },
    {
     "key": "pet_friendly_area",
     "label": "Área para mascotas",
     "alias": [
      "Pet park"
     ]
    }
   ]
  },
  {
   "grupo": "Exterior",
   "items": [
    {
     "key": "acceso_playa",
     "label": "Acceso a la playa"
    },
    {
     "key": "anden",
     "label": "Andén"
    },
    {
     "key": "balcon",
     "label": "Balcón"
    },
    {
     "key": "cisterna",
     "label": "Cisterna"
    },
    {
     "key": "estacionamiento_techado",
     "label": "Estacionamiento techado",
     "alias": [
      "Cochera techada"
     ]
    },
    {
     "key": "facil_estacionarse",
     "label": "Facilidad para estacionarse"
    },
    {
     "key": "frente_playa",
     "label": "Frente a la playa"
    },
    {
     "key": "frente_agua",
     "label": "Frente al agua"
    },
    {
     "key": "jardin",
     "label": "Jardín"
    },
    {
     "key": "patio",
     "label": "Patio"
    },
    {
     "key": "roof_garden",
     "label": "Roof garden",
     "alias": [
      "Roofgarden",
      "Azotea"
     ]
    },
    {
     "key": "terraza",
     "label": "Terraza"
    },
    {
     "key": "vista_agua",
     "label": "Vista al agua"
    },
    {
     "key": "vista_mar",
     "label": "Vista al mar"
    },
    {
     "key": "vista_panoramica",
     "label": "Vista panorámica"
    }
   ]
  },
  {
   "grupo": "General",
   "items": [
    {
     "key": "aire_acondicionado",
     "label": "Aire acondicionado",
     "alias": [
      "A/C",
      "Clima",
      "Minisplit"
     ]
    },
    {
     "key": "calefaccion",
     "label": "Calefacción"
    },
    {
     "key": "cocina_integral",
     "label": "Cocina integral",
     "alias": [
      "Cocina equipada"
     ]
    },
    {
     "key": "cuarto_servicio",
     "label": "Cuarto de servicio"
    },
    {
     "key": "dos_plantas",
     "label": "Dos plantas"
    },
    {
     "key": "elevador",
     "label": "Elevador",
     "alias": [
      "Ascensor"
     ]
    },
    {
     "key": "estudio",
     "label": "Estudio"
    },
    {
     "key": "fraccionamiento_privado",
     "label": "Fraccionamiento privado",
     "alias": [
      "Coto privado",
      "Privada"
     ]
    },
    {
     "key": "hidroneumatico",
     "label": "Hidroneumático"
    },
    {
     "key": "oficina",
     "label": "Oficina"
    },
    {
     "key": "panel_solar",
     "label": "Panel solar",
     "alias": [
      "Paneles solares",
      "Calentador solar"
     ]
    },
    {
     "key": "penthouse",
     "label": "Penthouse"
    },
    {
     "key": "planta_baja",
     "label": "Planta baja"
    },
    {
     "key": "planta_electrica",
     "label": "Planta eléctrica"
    },
    {
     "key": "portero",
     "label": "Portero",
     "alias": [
      "Conserje"
     ]
    },
    {
     "key": "rampas",
     "label": "Rampas",
     "alias": [
      "Accesibilidad"
     ]
    },
    {
     "key": "recamara_planta_baja",
     "label": "Recámara en planta baja"
    },
    {
     "key": "seguridad_12h",
     "label": "Seguridad 12 horas"
    },
    {
     "key": "seguridad_24h",
     "label": "Seguridad 24 horas",
     "alias": [
      "Seguridad 24h",
      "Vigilancia 24 horas",
      "Vigilancia 24h",
      "Seguridad"
     ]
    },
    {
     "key": "una_planta",
     "label": "Una sola planta"
    },
    {
     "key": "vestidor",
     "label": "Vestidor"
    },
    {
     "key": "amueblado",
     "label": "Amueblado",
     "alias": [
      "Amueblada"
     ]
    },
    {
     "key": "chimenea",
     "label": "Chimenea"
    },
    {
     "key": "closets",
     "label": "Closets",
     "alias": [
      "Clósets"
     ]
    },
    {
     "key": "bodega_interna",
     "label": "Bodega / cuarto de guardado",
     "alias": [
      "Bodega"
     ]
    },
    {
     "key": "internet",
     "label": "Internet / fibra óptica",
     "alias": [
      "Internet",
      "Fibra óptica",
      "Wifi"
     ]
    },
    {
     "key": "gas_estacionario",
     "label": "Gas estacionario",
     "alias": [
      "Gas natural"
     ]
    }
   ]
  },
  {
   "grupo": "Políticas",
   "items": [
    {
     "key": "mascotas_si",
     "label": "Mascotas permitidas",
     "alias": [
      "Se aceptan mascotas",
      "Pet friendly"
     ]
    },
    {
     "key": "mascotas_no",
     "label": "No se aceptan mascotas"
    },
    {
     "key": "fumar_si",
     "label": "Permitido fumar"
    },
    {
     "key": "fumar_no",
     "label": "Prohibido fumar"
    }
   ]
  },
  {
   "grupo": "Recreación",
   "items": [
    {
     "key": "alberca",
     "label": "Alberca",
     "alias": [
      "Piscina"
     ]
    },
    {
     "key": "juegos_infantiles",
     "label": "Área de juegos infantiles",
     "alias": [
      "Juegos infantiles",
      "Área infantil"
     ]
    },
    {
     "key": "padel",
     "label": "Cancha de pádel",
     "alias": [
      "Pádel"
     ]
    },
    {
     "key": "tenis",
     "label": "Cancha de tenis"
    },
    {
     "key": "cine",
     "label": "Cine",
     "alias": [
      "Sala de cine"
     ]
    },
    {
     "key": "fogatero",
     "label": "Fogatero"
    },
    {
     "key": "gimnasio",
     "label": "Gimnasio",
     "alias": [
      "Gym"
     ]
    },
    {
     "key": "jacuzzi",
     "label": "Jacuzzi"
    },
    {
     "key": "ludoteca",
     "label": "Ludoteca"
    },
    {
     "key": "salon_usos_multiples",
     "label": "Salón de usos múltiples",
     "alias": [
      "Salón de eventos",
      "SUM"
     ]
    },
    {
     "key": "sauna",
     "label": "Sauna",
     "alias": [
      "Vapor"
     ]
    },
    {
     "key": "cancha_futbol",
     "label": "Cancha de fútbol"
    },
    {
     "key": "cancha_basquetbol",
     "label": "Cancha de básquetbol"
    },
    {
     "key": "golf",
     "label": "Campo de golf",
     "alias": [
      "Golf"
     ]
    }
   ]
  },
  {
   "grupo": "Financiamiento aceptado",
   "items": [
    {
     "key": "fin_bancario",
     "label": "Créditos bancarios",
     "alias": [
      "Crédito bancario",
      "Crédito hipotecario"
     ]
    },
    {
     "key": "fin_infonavit",
     "label": "INFONAVIT / COFINAVIT",
     "alias": [
      "Infonavit",
      "Cofinavit"
     ]
    },
    {
     "key": "fin_fovissste",
     "label": "FOVISSSTE",
     "alias": [
      "Fovisste"
     ]
    },
    {
     "key": "fin_issfam",
     "label": "ISSFAM / Banjercito",
     "alias": [
      "Issfam",
      "Banjercito"
     ]
    },
    {
     "key": "fin_pemex",
     "label": "PEMEX",
     "alias": [
      "Pemex"
     ]
    }
   ]
  }
 ]
}/*__CATALOGO_FIN__*/;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var TIPO = {}, TIPO_GRUPO = {}, TIPO_FAM = {}, OP = {}, CAR = {}, CAR_GRUPO = {};
  CAT.tipos.forEach(function (g) { g.items.forEach(function (t) { TIPO[t.key] = t.label; TIPO_GRUPO[t.key] = g.grupo; TIPO_FAM[t.key] = t.familia; }); });
  CAT.operaciones.forEach(function (o) { OP[o.key] = o; });
  CAT.caracteristicas.forEach(function (g) { g.items.forEach(function (c) { CAR[c.key] = c.label; CAR_GRUPO[c.key] = g.grupo; }); });
  function mapa(lista) { var m = {}; lista.forEach(function (x) { m[x.key] = x.label; }); return m; }
  var PERIODO = mapa(CAT.periodos), UNIDAD = mapa(CAT.unidades);
  var CONDICION = mapa(CAT.condiciones), DISPOSICION = mapa(CAT.disposiciones), ORIENTACION = mapa(CAT.orientaciones);

  // Tipo detallado de un inmueble: subtipo (nuevo) o tipo (viejo).
  function tipoDe(p) { return p ? (p.subtipo || p.tipo || '') : ''; }
  function tipoLabel(k) { return TIPO[k] || (k ? String(k).charAt(0).toUpperCase() + String(k).slice(1) : ''); }
  function opLabel(k) { return OP[k] ? OP[k].label : (k || ''); }

  // <option>s agrupados por <optgroup>. opts.vacio = texto de la opción vacía.
  function tiposOptions(sel, opts) {
    opts = opts || {};
    var h = opts.vacio != null ? '<option value="">' + esc(opts.vacio) + '</option>' : '';
    CAT.tipos.forEach(function (g) {
      h += '<optgroup label="' + esc(g.grupo) + '">';
      g.items.forEach(function (t) {
        h += '<option value="' + t.key + '"' + (t.key === sel ? ' selected' : '') + '>' + esc(t.label) + '</option>';
      });
      h += '</optgroup>';
    });
    return h;
  }
  function listaOptions(lista, sel, vacio) {
    var h = vacio != null ? '<option value="">' + esc(vacio) + '</option>' : '';
    lista.forEach(function (x) { h += '<option value="' + x.key + '"' + (x.key === sel ? ' selected' : '') + '>' + esc(x.label) + '</option>'; });
    return h;
  }

  // Operaciones de un inmueble, normalizadas. Si el inmueble es viejo (sin
  // columna operaciones) se arma una a partir de operacion/precio/moneda.
  function operaciones(p) {
    if (!p) return [];
    var ops = Array.isArray(p.operaciones) ? p.operaciones.filter(function (o) { return o && o.tipo; }) : [];
    if (ops.length) return ops;
    if (!p.operacion) return [];
    return [{ tipo: p.operacion, precio: p.precio, moneda: p.moneda || 'MXN', unidad: p.precio_unidad || 'total' }];
  }
  function tieneOperacion(p, k) {
    return operaciones(p).some(function (o) { return o.tipo === k; });
  }
  function fmtMonto(n, moneda) {
    var v = Number(n);
    if (!isFinite(v) || v <= 0) return 'Precio a consultar';
    return '$' + v.toLocaleString('es-MX', { maximumFractionDigits: 0 }) + ' ' + (moneda || 'MXN');
  }
  function precioTexto(o) {
    if (!o) return '';
    var t = fmtMonto(o.precio, o.moneda);
    if (o.unidad && o.unidad !== 'total' && UNIDAD[o.unidad]) t += ' ' + UNIDAD[o.unidad];
    if (o.tipo === 'renta_temporal' && o.periodo && PERIODO[o.periodo]) t += ' ' + PERIODO[o.periodo];
    else if (o.tipo === 'renta') t += ' / mes';
    return t;
  }
  function caractLabel(k) { return CAR[k] || k; }
  function caractPorGrupo(keys) {
    var set = {};
    (keys || []).forEach(function (k) { set[k] = true; });
    var out = [];
    CAT.caracteristicas.forEach(function (g) {
      var items = g.items.filter(function (c) { return set[c.key]; }).map(function (c) { return c.label; });
      if (items.length) out.push({ grupo: g.grupo, items: items });
    });
    return out;
  }
  // Casillas agrupadas para formularios/filtros. name = atributo name.
  function caractCheckboxes(name, seleccion, opts) {
    opts = opts || {};
    var set = {};
    (seleccion || []).forEach(function (k) { set[k] = true; });
    var grupos = opts.soloGrupo ? CAT.caracteristicas.filter(function (g) { return g.grupo === opts.soloGrupo; }) : CAT.caracteristicas;
    return grupos.map(function (g) {
      return '<fieldset class="bk-car-grupo"><legend>' + esc(g.grupo) + '</legend><div class="bk-car-items">' +
        g.items.map(function (c) {
          return '<label class="bk-car-item"><input type="checkbox" name="' + esc(name) + '" value="' + c.key + '"' +
            (set[c.key] ? ' checked' : '') + '/><span>' + esc(c.label) + '</span></label>';
        }).join('') + '</div></fieldset>';
    }).join('');
  }

  // ── Multimedia ──
  // ID de YouTube de cualquier forma de liga (watch, youtu.be, shorts, embed, live).
  function ytId(url) {
    var m = String(url || '').match(/(?:youtu\.be\/|youtube(?:-nocookie)?\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/|live\/|v\/))([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
  }
  function esHttps(url) { return /^https:\/\/[^\s"'<>]+$/i.test(String(url || '').trim()); }
  function iframe(src, titulo) {
    return '<div class="bk-embed"><iframe src="' + esc(src) + '" title="' + esc(titulo) + '" loading="lazy" ' +
      'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; xr-spatial-tracking; fullscreen" ' +
      'allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe></div>';
  }
  function videoEmbed(url) {
    var id = ytId(url);
    return id ? iframe('https://www.youtube-nocookie.com/embed/' + id, 'Video del inmueble') : '';
  }
  function tourEmbed(url) {
    url = String(url || '').trim();
    if (!esHttps(url)) return '';
    // Matterport: la liga "show" se embebe tal cual; Kuula: /share/ → /share/ (embed acepta ambas).
    return iframe(url, 'Tour virtual');
  }
  // Limpia una lista de ligas (texto con saltos de línea o arreglo).
  function ligas(v, soloYoutube) {
    var arr = Array.isArray(v) ? v : String(v || '').split(/[\n,]+/);
    var out = [];
    arr.forEach(function (x) {
      x = String(x || '').trim();
      if (!x) return;
      if (soloYoutube) { var id = ytId(x); if (id) x = 'https://www.youtube.com/watch?v=' + id; else return; }
      else if (!esHttps(x)) return;
      if (out.indexOf(x) === -1) out.push(x);
    });
    return out;
  }
  function multimediaHtml(p, opts) {
    opts = opts || {};
    var h = '';
    var vids = (p.videos || []).map(videoEmbed).filter(Boolean);
    var tours = (p.tours || []).map(tourEmbed).filter(Boolean);
    var docs = (p.documentos || []).filter(function (d) { return d && esHttps(d.url); });
    if (vids.length) h += '<div class="bk-mm"><h4>' + (vids.length > 1 ? 'Videos' : 'Video') + '</h4>' + vids.join('') + '</div>';
    if (tours.length) h += '<div class="bk-mm"><h4>Tour virtual</h4>' + tours.join('') + '</div>';
    if (docs.length) h += '<div class="bk-mm"><h4>Documentos</h4><ul class="bk-docs">' + docs.map(function (d) {
      return '<li><a href="' + esc(d.url) + '" target="_blank" rel="noopener" download>' + esc(d.nombre || 'Documento') + '</a>' +
        (d.tamano ? ' <span>' + Math.max(1, Math.round(d.tamano / 1024)) + ' KB</span>' : '') + '</li>';
    }).join('') + '</ul></div>';
    return h;
  }

  window.BK_CAT = CAT;
  window.bkCat = {
    data: CAT,
    esc: esc,
    tipoLabel: tipoLabel,
    tipoDe: tipoDe,
    tipoFamilia: function (k) { return TIPO_FAM[k] || k || ''; },
    tipoGrupo: function (k) { return TIPO_GRUPO[k] || ''; },
    tiposOptions: tiposOptions,
    listaOptions: listaOptions,
    opLabel: opLabel,
    opLegacy: function (k) { return OP[k] ? OP[k].legacy : k; },
    operaciones: operaciones,
    tieneOperacion: tieneOperacion,
    precioTexto: precioTexto,
    fmtMonto: fmtMonto,
    periodoLabel: function (k) { return PERIODO[k] || ''; },
    unidadLabel: function (k) { return UNIDAD[k] || ''; },
    condicionLabel: function (k) { return CONDICION[k] || k || ''; },
    disposicionLabel: function (k) { return DISPOSICION[k] || k || ''; },
    orientacionLabel: function (k) { return ORIENTACION[k] || k || ''; },
    caractLabel: caractLabel,
    caractGrupo: function (k) { return CAR_GRUPO[k] || ''; },
    caractPorGrupo: caractPorGrupo,
    caractCheckboxes: caractCheckboxes,
    ytId: ytId,
    esHttps: esHttps,
    videoEmbed: videoEmbed,
    tourEmbed: tourEmbed,
    ligas: ligas,
    multimediaHtml: multimediaHtml
  };
  // Estilos mínimos de multimedia (la usan páginas con hojas distintas).
  if (typeof document !== 'undefined' && !document.getElementById('bk-mm-css')) {
    var st = document.createElement('style'); st.id = 'bk-mm-css';
    st.textContent = '.bk-embed{position:relative;width:100%;aspect-ratio:16/9;border-radius:var(--r,12px);overflow:hidden;background:var(--paper-2,#eee);margin:0 0 10px}' +
      '.bk-embed iframe{position:absolute;inset:0;width:100%;height:100%;border:0}' +
      '.bk-mm{margin:14px 0}.bk-mm h4{margin:0 0 8px;font-size:var(--fs-sm,14px);font-weight:600}' +
      '.bk-docs{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:6px}' +
      '.bk-docs a{font-weight:600;color:inherit;text-decoration:underline}.bk-docs span{color:var(--mute,#777);font-size:var(--fs-xs,12px)}';
    (document.head || document.documentElement).appendChild(st);
  }
})();
