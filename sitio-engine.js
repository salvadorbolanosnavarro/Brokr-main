/* ═══════════════════════════════════════════════════════════════════════
   BROQUER · MOTOR DEL SITIO PÚBLICO DE AGENTES · v2
   Una sola fuente de verdad para ambas plantillas — la personalidad de
   cada una vive en sitio.css vía [data-template="editorial"|"ejecutiva"].
   ═══════════════════════════════════════════════════════════════════════ */

const SB_URL = 'https://urtgysmtnvoqaljuhntz.supabase.co';
const API_BASE = 'https://api.broquer.app';
const SB_KEY = 'sb_publishable_EVGLfmHVorBpQQWAh-vypA_hANNk_-i';

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function sbPublic(path) {
  const r = await fetch(`${SB_URL}/rest/v1/${path}`, { headers: { apikey: SB_KEY } });
  if (!r.ok) throw new Error('Error de conexión (' + r.status + ')');
  return r.json();
}

function money(n) {
  if (n == null) return null;
  try { return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 }).format(n); }
  catch { return '$' + n; }
}

function precioTexto(p) {
  if (p.operacion === 'renta') {
    return p.precio_renta != null ? money(p.precio_renta) + ' / mes' : 'Precio a consultar';
  }
  return p.precio != null ? money(p.precio) : 'Precio a consultar';
}
function precioNumerico(p) {
  const v = p.operacion === 'renta' ? p.precio_renta : p.precio;
  return v == null ? null : Number(v);
}

function waLink(tel, mensaje) {
  const digits = String(tel || '').replace(/\D/g, '');
  if (!digits) return null;
  const num = digits.length === 10 ? '52' + digits : digits;
  return 'https://wa.me/' + num + (mensaje ? '?text=' + encodeURIComponent(mensaje) : '');
}

function iniciales(nombre) {
  const p = String(nombre || '?').trim().split(/\s+/);
  return (p.length >= 2 ? p[0][0] + p[1][0] : String(nombre || '??').slice(0, 2)).toUpperCase();
}

function redSocialLink(tipo, valor) {
  if (!valor) return null;
  if (/^https?:\/\//i.test(valor)) return valor;
  const user = valor.replace(/^@/, '');
  if (tipo === 'instagram') return 'https://instagram.com/' + user;
  if (tipo === 'facebook') return 'https://facebook.com/' + user;
  if (tipo === 'tiktok') return 'https://tiktok.com/@' + user;
  return null;
}

function tipoLegible(t) {
  const mapa = { casa:'Casa', departamento:'Departamento', depa:'Departamento', terreno:'Terreno', local:'Local comercial', oficina:'Oficina', bodega:'Bodega', edificio:'Edificio' };
  const k = String(t || '').toLowerCase();
  return mapa[k] || (t ? t.charAt(0).toUpperCase() + t.slice(1) : 'Propiedad');
}

/* ── Extraer el slug de la URL actual ─────────────────────────────────── */
function slugDesdeUrl() {
  const params = new URLSearchParams(location.search);
  if (params.get('slug')) return params.get('slug');
  const path = location.pathname.replace(/^\/+|\/+$/g, '');
  if (!path) return null;
  if (path.includes('/')) return null;
  if (/\.[a-z0-9]+$/i.test(path)) return null;
  return path;
}

/* ── Estados especiales ────────────────────────────────────────────────── */
function renderNoEncontrado() {
  document.title = 'Página no encontrada · Broquer';
  document.getElementById('sitio-root').innerHTML = `
    <div class="nf-wrap">
      <div class="nf-box">
        <h1>Este sitio no existe</h1>
        <p>El link que buscas no está activo o no existe. Si eres el dueño de este sitio, revisa que esté activado en tu panel de Broquer.</p>
        <a class="nf-link" href="https://broquer.app">Ir a Broquer →</a>
      </div>
    </div>
  `;
}
function renderError(msg) {
  document.getElementById('sitio-root').innerHTML = `
    <div class="nf-wrap">
      <div class="nf-box">
        <h1>No se pudo cargar el sitio</h1>
        <p>${esc(msg || 'Intenta de nuevo en unos segundos.')}</p>
      </div>
    </div>
  `;
}

/* ── Carga principal ───────────────────────────────────────────────────── */
let _perfil = null;
let _propsTodas = [];
let _propsVisibles = [];
let _filtro = { operacion: '', tipo: '', texto: '', orden: 'reciente', ciudad: '', colonia: '', precioMin: null, precioMax: null, recamaras: 0 };

async function cargarSitio() {
  const slug = slugDesdeUrl();
  if (!slug) { renderNoEncontrado(); return; }

  let perfil;
  try {
    const rows = await sbPublic('usuarios_publicos?slug=eq.' + encodeURIComponent(slug) + '&select=*&limit=1');
    perfil = Array.isArray(rows) && rows[0];
  } catch (e) { renderError(e.message); return; }

  if (!perfil) { renderNoEncontrado(); return; }
  _perfil = perfil;

  document.body.dataset.template = perfil.sitio_template === 'ejecutiva' ? 'ejecutiva' : 'editorial';
  document.body.dataset.whatsappActual = perfil.whatsapp_publico || '';
  document.title = (perfil.nombre_publico || 'Agente inmobiliario') + ' · Sitio oficial';
  setMetaDescripcion(
    (perfil.nombre_publico || 'Agente inmobiliario') +
    (perfil.zona_cobertura ? ' — ' + perfil.zona_cobertura : '') +
    '. Encuentra tu próxima propiedad y contáctame directo por WhatsApp.'
  );

  let props = [], testimonios = [];
  try {
    [props, testimonios] = await Promise.all([
      sbPublic('propiedades_publicas?user_id=eq.' + encodeURIComponent(perfil.id)
        // 'no_activa' son inmuebles que la IA dio de alta con lo que le mando
        // un tercero por WhatsApp: sin verificar. Jamas se publican.
        + '&estatus=not.in.(no_activa)&select=*&order=updated_at.desc&limit=200'),
      sbPublic('testimonios_publicos?user_id=eq.' + encodeURIComponent(perfil.id) + '&select=*&order=created_at.desc&limit=50'),
    ]);
  } catch (e) { /* si truena, mostramos el sitio igual sin esas secciones */ }

  _propsTodas = Array.isArray(props) ? props : [];
  _propsVisibles = _propsTodas.slice();
  render(perfil, Array.isArray(testimonios) ? testimonios : []);
}

function setMetaDescripcion(texto) {
  let tag = document.querySelector('meta[name="description"]');
  if (!tag) {
    tag = document.createElement('meta');
    tag.setAttribute('name', 'description');
    document.head.appendChild(tag);
  }
  tag.setAttribute('content', texto);
}

/* ── Render de página completa ─────────────────────────────────────────── */
function render(perfil, testimonios) {
  const redes = perfil.redes || {};
  const waMensajeGeneral = 'Hola ' + (perfil.nombre_publico || '') + ', vi tu sitio y me gustaría más información.';
  const waPerfil = waLink(perfil.whatsapp_publico, waMensajeGeneral);
  const hayTestimonios = testimonios.length > 0;

  const navHtml = `
    <header class="st-nav">
      <div class="st-nav__inner">
        <a class="st-nav__marca" href="#top">${esc(perfil.nombre_publico || 'Agente')}</a>
        <nav class="st-nav__links">
          <a href="#propiedades">Propiedades</a>
          <a href="#sobre-mi">Sobre mí</a>
          ${hayTestimonios ? '<a href="#testimonios">Testimonios</a>' : ''}
          <a href="#contacto">Contacto</a>
        </nav>
        ${waPerfil ? `<a class="st-nav__cta" href="${waPerfil}" target="_blank" rel="noopener">WhatsApp</a>` : ''}
      </div>
    </header>
  `;

  const statChips = [
    perfil.anos_experiencia ? { n: perfil.anos_experiencia, lbl: 'Años de experiencia' } : null,
    { n: _propsTodas.length, lbl: _propsTodas.length === 1 ? 'Propiedad disponible' : 'Propiedades disponibles' },
    hayTestimonios ? { n: testimonios.length, lbl: testimonios.length === 1 ? 'Cliente satisfecho' : 'Clientes satisfechos' } : null,
  ].filter(Boolean);

  const heroHtml = `
    <section class="st-hero" id="top">
      <div class="st-hero__inner">
        <div class="st-hero__foto">
          ${perfil.foto_url ? `<img src="${esc(perfil.foto_url)}" alt="${esc(perfil.nombre_publico || '')}"/>` : `<span>${esc(iniciales(perfil.nombre_publico))}</span>`}
        </div>
        <div class="st-hero__texto">
          <div class="st-hero__kicker">Agente inmobiliario${perfil.zona_cobertura ? ' · ' + esc(perfil.zona_cobertura) : ''}</div>
          <h1>${esc(perfil.nombre_publico || 'Agente inmobiliario')}</h1>
          ${perfil.bio ? `<p class="st-hero__bio">${esc(perfil.bio)}</p>` : ''}
          <div class="st-hero__acts">
            ${waPerfil ? `<a class="st-btn st-btn--primary" href="${waPerfil}" target="_blank" rel="noopener">${ICONO_WA_INLINE} Contactar por WhatsApp</a>` : ''}
            <a class="st-btn st-btn--ghost" href="#propiedades">Ver propiedades</a>
          </div>
          <div class="st-social-row">
            ${redSocialLink('instagram', redes.instagram) ? `<a class="st-social" href="${esc(redSocialLink('instagram', redes.instagram))}" target="_blank" rel="noopener" aria-label="Instagram">${ICONO_IG}</a>` : ''}
            ${redSocialLink('facebook', redes.facebook) ? `<a class="st-social" href="${esc(redSocialLink('facebook', redes.facebook))}" target="_blank" rel="noopener" aria-label="Facebook">${ICONO_FB}</a>` : ''}
            ${redSocialLink('tiktok', redes.tiktok) ? `<a class="st-social" href="${esc(redSocialLink('tiktok', redes.tiktok))}" target="_blank" rel="noopener" aria-label="TikTok">${ICONO_TT}</a>` : ''}
          </div>
        </div>
      </div>
      ${statChips.length ? `<div class="st-stats">
        ${statChips.map(s => `<div class="st-stat"><div class="st-stat__n">${esc(String(s.n))}</div><div class="st-stat__lbl">${esc(s.lbl)}</div></div>`).join('')}
      </div>` : ''}
    </section>
  `;

  const propsHtml = `
    <section class="st-props" id="propiedades">
      <h2 class="st-h2">Propiedades disponibles</h2>
      ${_propsTodas.length ? buscadorHtml() : ''}
      <div class="st-grid-count" id="st-grid-count"></div>
      <div class="st-grid" id="st-grid"></div>
    </section>
  `;

  const sobreMiHtml = `
    <section class="st-sobre" id="sobre-mi">
      <h2 class="st-h2">Sobre mí</h2>
      <div class="st-sobre__box">
        ${perfil.bio ? `<p>${esc(perfil.bio)}</p>` : `<p>Agente inmobiliario${perfil.zona_cobertura ? ' en ' + esc(perfil.zona_cobertura) : ''}, listo para ayudarte a encontrar tu próxima propiedad o vender la tuya al mejor precio.</p>`}
        <div class="st-sobre__datos">
          ${perfil.zona_cobertura ? `<div><span>Zona de cobertura</span><strong>${esc(perfil.zona_cobertura)}</strong></div>` : ''}
          ${perfil.anos_experiencia ? `<div><span>Experiencia</span><strong>${esc(String(perfil.anos_experiencia))} años</strong></div>` : ''}
          ${perfil.whatsapp_publico ? `<div><span>Contacto directo</span><strong>${esc(perfil.whatsapp_publico)}</strong></div>` : ''}
        </div>
      </div>
    </section>
  `;

  const testiHtml = hayTestimonios ? `
    <section class="st-testis" id="testimonios">
      <h2 class="st-h2">Lo que dicen mis clientes</h2>
      <div class="st-testis__grid">
        ${testimonios.map(t => `<div class="st-testi">
          ${t.calificacion ? `<div class="st-testi__stars">${'★'.repeat(t.calificacion)}${'☆'.repeat(5 - t.calificacion)}</div>` : ''}
          <p class="st-testi__texto">“${esc(t.texto)}”</p>
          <div class="st-testi__nombre">${esc(t.nombre_cliente)}</div>
        </div>`).join('')}
      </div>
    </section>
  ` : '';

  const contactoHtml = `
    <section class="st-contacto" id="contacto">
      <h2 class="st-h2">Hablemos</h2>
      <div class="st-contacto__box">
        <div class="st-contacto__info">
          <p>Cuéntame qué buscas y te respondo directo por WhatsApp.</p>
          ${perfil.whatsapp_publico ? `<div class="st-contacto__tel">${esc(perfil.whatsapp_publico)}</div>` : ''}
        </div>
        <form class="st-form" id="st-form" onsubmit="return enviarContacto(event)">
          <input type="text" id="cf-nombre" placeholder="Tu nombre" required/>
          <input type="tel" id="cf-tel" placeholder="Tu teléfono (opcional)"/>
          <input type="text" id="cf-sitio-web" name="sitio_web" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px;height:0;width:0;opacity:0" aria-hidden="true"/>
          <textarea id="cf-mensaje" placeholder="¿Qué tipo de propiedad buscas?" required></textarea>
          <button type="submit" class="st-btn st-btn--primary">${ICONO_WA_INLINE} Enviar por WhatsApp</button>
        </form>
      </div>
    </section>
  `;

  const footerHtml = `
    <footer class="st-footer">
      <div class="st-footer__cols">
        <div class="st-footer__col">
          <div class="st-footer__marca">${esc(perfil.nombre_publico || '')}</div>
          ${perfil.zona_cobertura ? `<div class="st-footer__muted">${esc(perfil.zona_cobertura)}</div>` : ''}
          <div class="st-social-row">
            ${redSocialLink('instagram', redes.instagram) ? `<a class="st-social st-social--sm" href="${esc(redSocialLink('instagram', redes.instagram))}" target="_blank" rel="noopener" aria-label="Instagram">${ICONO_IG}</a>` : ''}
            ${redSocialLink('facebook', redes.facebook) ? `<a class="st-social st-social--sm" href="${esc(redSocialLink('facebook', redes.facebook))}" target="_blank" rel="noopener" aria-label="Facebook">${ICONO_FB}</a>` : ''}
            ${redSocialLink('tiktok', redes.tiktok) ? `<a class="st-social st-social--sm" href="${esc(redSocialLink('tiktok', redes.tiktok))}" target="_blank" rel="noopener" aria-label="TikTok">${ICONO_TT}</a>` : ''}
          </div>
        </div>
        <div class="st-footer__col">
          <div class="st-footer__hdr">Navegación</div>
          <a href="#propiedades">Propiedades</a>
          <a href="#sobre-mi">Sobre mí</a>
          ${hayTestimonios ? '<a href="#testimonios">Testimonios</a>' : ''}
          <a href="#contacto">Contacto</a>
        </div>
        <div class="st-footer__col">
          <div class="st-footer__hdr">Legal</div>
          <a href="aviso-privacidad.html">Aviso de privacidad</a>
        </div>
      </div>
      <div class="st-footer__bar">
        <span>© ${new Date().getFullYear()} ${esc(perfil.nombre_publico || '')}</span>
        <a href="https://broquer.app" class="st-credito">Hecho con Broquer</a>
      </div>
    </footer>
  `;

  const waFloat = waPerfil ? `<a class="st-wa-float" href="${waPerfil}" target="_blank" rel="noopener" aria-label="WhatsApp">${ICONO_WA}</a>` : '';

  document.getElementById('sitio-root').innerHTML =
    navHtml + heroHtml + propsHtml + sobreMiHtml + testiHtml + contactoHtml + footerHtml + waFloat;

  renderGrid();
  bindBuscador();
}

/* ── Buscador / filtros ────────────────────────────────────────────────── */
function buscadorHtml() {
  const tipos = [...new Set(_propsTodas.map(p => p.tipo).filter(Boolean))].sort();
  const ciudades = [...new Set(_propsTodas.map(p => p.ciudad).filter(Boolean))].sort();
  return `
    <div class="st-buscador">
      <div class="st-buscador__top">
        <div class="st-buscador__tabs">
          <button type="button" class="st-tab is-active" data-op="">Todas</button>
          <button type="button" class="st-tab" data-op="venta">Venta</button>
          <button type="button" class="st-tab" data-op="renta">Renta</button>
        </div>
        <select id="st-f-orden" class="st-f-orden">
          <option value="reciente">Más recientes</option>
          <option value="precio_asc">Precio: menor a mayor</option>
          <option value="precio_desc">Precio: mayor a menor</option>
        </select>
      </div>
      <input type="text" id="st-f-texto" placeholder="Buscar por colonia, ciudad o título…"/>
      <div class="st-buscador__filtros">
        <select id="st-f-tipo">
          <option value="">Todos los tipos</option>
          ${tipos.map(t => `<option value="${esc(t)}">${esc(tipoLegible(t))}</option>`).join('')}
        </select>
        <select id="st-f-ciudad" ${ciudades.length < 2 ? 'style="display:none"' : ''}>
          <option value="">Todas las ciudades</option>
          ${ciudades.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('')}
        </select>
        <select id="st-f-colonia">
          <option value="">Todas las colonias</option>
        </select>
        <select id="st-f-rec">
          <option value="0">Recámaras: todas</option>
          <option value="1">1+ recámaras</option>
          <option value="2">2+ recámaras</option>
          <option value="3">3+ recámaras</option>
          <option value="4">4+ recámaras</option>
        </select>
        <input type="number" id="st-f-pmin" inputmode="numeric" min="0" placeholder="Precio mín."/>
        <input type="number" id="st-f-pmax" inputmode="numeric" min="0" placeholder="Precio máx."/>
      </div>
    </div>
  `;
}

function poblarColonias() {
  const sel = document.getElementById('st-f-colonia');
  if (!sel) return;
  const base = _filtro.ciudad ? _propsTodas.filter(p => p.ciudad === _filtro.ciudad) : _propsTodas;
  const colonias = [...new Set(base.map(p => p.colonia).filter(Boolean))].sort();
  const actual = _filtro.colonia;
  sel.innerHTML = '<option value="">Todas las colonias</option>' +
    colonias.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
  if (colonias.includes(actual)) sel.value = actual;
  else { sel.value = ''; _filtro.colonia = ''; }
}

function bindBuscador() {
  if (!_propsTodas.length) return;
  document.querySelectorAll('.st-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.st-tab').forEach(b => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      _filtro.operacion = btn.dataset.op;
      aplicarFiltros();
    });
  });
  const texto = document.getElementById('st-f-texto');
  let deb = null;
  texto.addEventListener('input', () => {
    clearTimeout(deb);
    deb = setTimeout(() => { _filtro.texto = texto.value.trim().toLowerCase(); aplicarFiltros(); }, 200);
  });
  document.getElementById('st-f-tipo').addEventListener('change', (e) => { _filtro.tipo = e.target.value; aplicarFiltros(); });
  document.getElementById('st-f-orden').addEventListener('change', (e) => { _filtro.orden = e.target.value; aplicarFiltros(); });
  document.getElementById('st-f-ciudad').addEventListener('change', (e) => { _filtro.ciudad = e.target.value; poblarColonias(); aplicarFiltros(); });
  document.getElementById('st-f-colonia').addEventListener('change', (e) => { _filtro.colonia = e.target.value; aplicarFiltros(); });
  document.getElementById('st-f-rec').addEventListener('change', (e) => { _filtro.recamaras = parseInt(e.target.value, 10) || 0; aplicarFiltros(); });
  let debP = null;
  const leerPrecios = () => {
    const min = document.getElementById('st-f-pmin').value, max = document.getElementById('st-f-pmax').value;
    _filtro.precioMin = min !== '' ? Number(min) : null;
    _filtro.precioMax = max !== '' ? Number(max) : null;
    aplicarFiltros();
  };
  ['st-f-pmin','st-f-pmax'].forEach(id => document.getElementById(id).addEventListener('input', () => {
    clearTimeout(debP); debP = setTimeout(leerPrecios, 300);
  }));
  poblarColonias();
}

function aplicarFiltros() {
  let lista = _propsTodas.filter(p => {
    if (_filtro.operacion && p.operacion !== _filtro.operacion) return false;
    if (_filtro.tipo && p.tipo !== _filtro.tipo) return false;
    if (_filtro.ciudad && p.ciudad !== _filtro.ciudad) return false;
    if (_filtro.colonia && p.colonia !== _filtro.colonia) return false;
    if (_filtro.recamaras && !(Number(p.recamaras) >= _filtro.recamaras)) return false;
    if (_filtro.precioMin != null || _filtro.precioMax != null) {
      const precio = precioNumerico(p);
      if (precio == null) return false;
      if (_filtro.precioMin != null && precio < _filtro.precioMin) return false;
      if (_filtro.precioMax != null && precio > _filtro.precioMax) return false;
    }
    if (_filtro.texto) {
      const blob = [p.titulo, p.colonia, p.ciudad].filter(Boolean).join(' ').toLowerCase();
      if (!blob.includes(_filtro.texto)) return false;
    }
    return true;
  });
  if (_filtro.orden === 'precio_asc' || _filtro.orden === 'precio_desc') {
    const dir = _filtro.orden === 'precio_asc' ? 1 : -1;
    lista = lista.slice().sort((a, b) => {
      const pa = precioNumerico(a), pb = precioNumerico(b);
      if (pa == null && pb == null) return 0;
      if (pa == null) return 1;
      if (pb == null) return -1;
      return (pa - pb) * dir;
    });
  }
  _propsVisibles = lista;
  renderGrid();
}

function renderGrid() {
  const cont = document.getElementById('st-grid');
  const contador = document.getElementById('st-grid-count');
  if (!cont) return;
  if (!_propsTodas.length) {
    cont.innerHTML = `<div class="st-vacio">Por ahora no hay propiedades publicadas. Vuelve pronto.</div>`;
    if (contador) contador.innerHTML = '';
    return;
  }
  if (contador) {
    contador.textContent = _propsVisibles.length === _propsTodas.length
      ? ''
      : _propsVisibles.length + ' de ' + _propsTodas.length + ' propiedades';
  }
  if (!_propsVisibles.length) {
    cont.innerHTML = `<div class="st-vacio">Ninguna propiedad coincide con tu búsqueda. <button type="button" class="st-link-btn" onclick="limpiarFiltros()">Quitar filtros</button></div>`;
    return;
  }
  cont.innerHTML = _propsVisibles.map((p, i) => tarjetaProp(p, i)).join('');
  cont.querySelectorAll('.st-card').forEach(el => {
    el.addEventListener('click', () => toggleDetalleProp(el.dataset.idx));
  });
}

function limpiarFiltros() {
  _filtro = { operacion: '', tipo: '', texto: '', orden: 'reciente', ciudad: '', colonia: '', precioMin: null, precioMax: null, recamaras: 0 };
  ['st-f-texto','st-f-pmin','st-f-pmax'].forEach(id => { const e = document.getElementById(id); if (e) e.value = ''; });
  ['st-f-tipo','st-f-ciudad','st-f-colonia'].forEach(id => { const e = document.getElementById(id); if (e) e.value = ''; });
  const rec = document.getElementById('st-f-rec'); if (rec) rec.value = '0';
  const orden = document.getElementById('st-f-orden'); if (orden) orden.value = 'reciente';
  poblarColonias();
  document.querySelectorAll('.st-tab').forEach(b => b.classList.toggle('is-active', b.dataset.op === ''));
  _propsVisibles = _propsTodas.slice();
  renderGrid();
}

/* ── Tarjeta + modal de detalle ─────────────────────────────────────────── */
function tarjetaProp(p, i) {
  const foto = Array.isArray(p.fotos) && p.fotos[0] ? p.fotos[0] : null;
  const ubic = [p.colonia, p.ciudad].filter(Boolean).join(', ');
  return `<article class="st-card" data-idx="${i}">
    <div class="st-card__foto">
      ${foto ? `<img src="${esc(foto)}" loading="lazy" decoding="async" alt=""/>` : `<div class="st-card__sinfoto">Sin foto</div>`}
      <span class="st-card__op">${p.operacion === 'renta' ? 'Renta' : 'Venta'}</span>
    </div>
    <div class="st-card__info">
      <div class="st-card__precio">${esc(precioTexto(p))}</div>
      <div class="st-card__titulo">${esc(p.titulo || 'Propiedad')}</div>
      ${ubic ? `<div class="st-card__ubic">${esc(ubic)}</div>` : ''}
      <div class="st-card__specs">
        ${p.recamaras ? `<span>${p.recamaras} rec</span>` : ''}
        ${p.banos ? `<span>${p.banos} baños</span>` : ''}
        ${p.m2_construccion ? `<span>${p.m2_construccion} m²</span>` : ''}
      </div>
    </div>
  </article>`;
}

function toggleDetalleProp(idxStr) {
  const idx = parseInt(idxStr, 10);
  const p = _propsVisibles[idx];
  if (!p) return;
  const fotos = Array.isArray(p.fotos) && p.fotos.length ? p.fotos : [];
  const ubic = [p.colonia, p.ciudad].filter(Boolean).join(', ');
  const wa = waLink(document.body.dataset.whatsappActual, 'Hola, me interesa esta propiedad: ' + (p.titulo || '') + (ubic ? ' (' + ubic + ')' : ''));
  const overlay = document.createElement('div');
  overlay.className = 'st-modal-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  overlay.innerHTML = `<div class="st-modal">
    <button class="st-modal__x" onclick="this.closest('.st-modal-overlay').remove()" aria-label="Cerrar"><svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 18L18 6M6 6l12 12"/></svg></button>
    <div class="st-modal__fotos">
      ${fotos.length ? fotos.map(f => `<img src="${esc(f)}" loading="lazy"/>`).join('') : '<div class="st-card__sinfoto">Sin fotos</div>'}
    </div>
    <div class="st-modal__body">
      <div class="st-modal__precio">${esc(precioTexto(p))}</div>
      <h3>${esc(p.titulo || 'Propiedad')}</h3>
      ${ubic ? `<div class="st-modal__ubic">${esc(ubic)}</div>` : ''}
      <div class="st-modal__specs">
        ${p.recamaras ? `<span>${p.recamaras} recámaras</span>` : ''}
        ${p.banos ? `<span>${p.banos} baños</span>` : ''}
        ${p.m2_terreno ? `<span>${p.m2_terreno} m² terreno</span>` : ''}
        ${p.m2_construccion ? `<span>${p.m2_construccion} m² construcción</span>` : ''}
      </div>
      ${p.descripcion ? `<p class="st-modal__desc">${esc(p.descripcion)}</p>` : ''}
      ${wa ? `<a class="st-btn st-btn--primary" href="${wa}" target="_blank" rel="noopener">${ICONO_WA_INLINE} Preguntar por esta propiedad</a>` : ''}
    </div>
  </div>`;
  document.body.appendChild(overlay);
}

/* ── Formulario de contacto: registra el lead en el CRM del agente y
   después abre WhatsApp. Si el registro falla, WhatsApp se abre igual
   (el visitante nunca se queda bloqueado). ─────────────────────────── */
function enviarContacto(ev) {
  ev.preventDefault();
  const nombre = document.getElementById('cf-nombre').value.trim();
  const tel = document.getElementById('cf-tel').value.trim();
  const mensaje = document.getElementById('cf-mensaje').value.trim();
  const hp = (document.getElementById('cf-sitio-web') || {}).value || '';

  // Registro del lead en Broquer (no bloqueante; keepalive sobrevive a la navegación)
  const slug = slugDesdeUrl();
  if (slug && nombre) {
    try {
      fetch(API_BASE + '/sitio/' + encodeURIComponent(slug) + '/lead', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        keepalive: true,
        body: JSON.stringify({ nombre, telefono: tel, mensaje, sitio_web: hp })
      }).catch(() => {});
    } catch (e) { /* nunca bloquear al visitante */ }
  }

  const texto = 'Hola, soy ' + nombre + (tel ? ' (tel: ' + tel + ')' : '') + '. ' + mensaje;
  const link = waLink(_perfil && _perfil.whatsapp_publico, texto);
  if (link) window.open(link, '_blank');
  return false;
}

/* ── Iconos ─────────────────────────────────────────────────────────────── */
const ICONO_WA = '<svg width="26" height="26" viewBox="0 0 32 32" fill="currentColor"><path d="M16 0C7.163 0 0 7.163 0 16c0 2.823.736 5.474 2.029 7.776L0 32l8.42-2.207A15.9 15.9 0 0016 32c8.837 0 16-7.163 16-16S24.837 0 16 0zm7.45 19.2c-.39-.196-2.31-1.142-2.668-1.273-.358-.13-.618-.196-.878.196-.26.39-1.008 1.272-1.236 1.532-.228.26-.456.293-.846.098-.39-.196-1.65-.61-3.143-1.94-1.162-1.037-1.948-2.318-2.176-2.708-.228-.39-.024-.6.171-.795.176-.175.39-.456.586-.683.196-.228.26-.39.39-.65.13-.26.065-.488-.033-.683-.098-.196-.878-2.117-1.203-2.9-.317-.762-.64-.66-.879-.672-.227-.012-.487-.014-.747-.014-.26 0-.683.098-1.04.488-.358.39-1.366 1.336-1.366 3.257 0 1.92 1.398 3.778 1.594 4.038.195.26 2.752 4.203 6.667 5.893.93.402 1.657.642 2.223.821.934.297 1.785.255 2.457.155.75-.112 2.31-.945 2.636-1.857.325-.911.325-1.692.228-1.857-.098-.165-.358-.26-.748-.456z"/></svg>';
const ICONO_WA_INLINE = '<svg width="16" height="16" viewBox="0 0 32 32" fill="currentColor" style="flex-shrink:0"><path d="M16 0C7.163 0 0 7.163 0 16c0 2.823.736 5.474 2.029 7.776L0 32l8.42-2.207A15.9 15.9 0 0016 32c8.837 0 16-7.163 16-16S24.837 0 16 0zm7.45 19.2c-.39-.196-2.31-1.142-2.668-1.273-.358-.13-.618-.196-.878.196-.26.39-1.008 1.272-1.236 1.532-.228.26-.456.293-.846.098-.39-.196-1.65-.61-3.143-1.94-1.162-1.037-1.948-2.318-2.176-2.708-.228-.39-.024-.6.171-.795.176-.175.39-.456.586-.683.196-.228.26-.39.39-.65.13-.26.065-.488-.033-.683-.098-.196-.878-2.117-1.203-2.9-.317-.762-.64-.66-.879-.672-.227-.012-.487-.014-.747-.014-.26 0-.683.098-1.04.488-.358.39-1.366 1.336-1.366 3.257 0 1.92 1.398 3.778 1.594 4.038.195.26 2.752 4.203 6.667 5.893.93.402 1.657.642 2.223.821.934.297 1.785.255 2.457.155.75-.112 2.31-.945 2.636-1.857.325-.911.325-1.692.228-1.857-.098-.165-.358-.26-.748-.456z"/></svg>';
const ICONO_IG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg>';
const ICONO_FB = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M13.5 21v-8h2.7l.4-3.1h-3.1V8c0-.9.25-1.5 1.55-1.5H16.7V3.7C16.4 3.65 15.4 3.56 14.25 3.56c-2.4 0-4.05 1.47-4.05 4.16V9.9H7.5V13h2.7v8h3.3z"/></svg>';
const ICONO_TT = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 2c.3 2.1 1.7 3.7 3.8 3.9v2.6c-1.4.1-2.7-.3-3.8-1v6.6c0 3.2-2.6 5.7-5.7 5.7S5 16.3 5 13.1c0-3.1 2.4-5.6 5.5-5.7v2.7c-1.5.1-2.7 1.4-2.7 3 0 1.7 1.4 3 3 3s3.1-1.3 3.1-3V2h2.6z"/></svg>';

document.addEventListener('DOMContentLoaded', cargarSitio);
