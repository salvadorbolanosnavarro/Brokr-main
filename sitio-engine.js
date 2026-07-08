/* ═══════════════════════════════════════════════════════════════════════
   BROQUER · MOTOR DEL SITIO PÚBLICO DE AGENTES
   Usado por sitio.html (pruebas con ?slug=) y 404.html (producción,
   atrapa broquer.app/tu-slug). Una sola fuente de verdad para ambas
   plantillas — la personalidad de cada una vive en sitio.css via
   [data-template="editorial"|"ejecutiva"], no en JS duplicado.
   ═══════════════════════════════════════════════════════════════════════ */

const SB_URL = 'https://urtgysmtnvoqaljuhntz.supabase.co';
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

/* ── Extraer el slug de la URL actual ─────────────────────────────────── */
function slugDesdeUrl() {
  const params = new URLSearchParams(location.search);
  if (params.get('slug')) return params.get('slug');
  const path = location.pathname.replace(/^\/+|\/+$/g, '');
  if (!path) return null;
  if (path.includes('/')) return null; // rutas con más de un segmento no son un slug de agente
  if (/\.[a-z0-9]+$/i.test(path)) return null; // parece un archivo (tiene extensión), no un slug
  return path;
}

/* ── Estado "no encontrado" ────────────────────────────────────────────── */
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
async function cargarSitio() {
  const slug = slugDesdeUrl();
  if (!slug) { renderNoEncontrado(); return; }

  let perfil;
  try {
    const rows = await sbPublic('usuarios_publicos?slug=eq.' + encodeURIComponent(slug) + '&select=*&limit=1');
    perfil = Array.isArray(rows) && rows[0];
  } catch (e) { renderError(e.message); return; }

  if (!perfil) { renderNoEncontrado(); return; }

  document.body.dataset.template = perfil.sitio_template === 'ejecutiva' ? 'ejecutiva' : 'editorial';
  document.body.dataset.whatsappActual = perfil.whatsapp_publico || '';
  document.title = (perfil.nombre_publico || 'Agente inmobiliario') + ' · Broquer';

  let props = [], testimonios = [];
  try {
    [props, testimonios] = await Promise.all([
      sbPublic('propiedades_publicas?user_id=eq.' + encodeURIComponent(perfil.id) + '&select=*&order=updated_at.desc&limit=200'),
      sbPublic('testimonios_publicos?user_id=eq.' + encodeURIComponent(perfil.id) + '&select=*&order=created_at.desc&limit=50'),
    ]);
  } catch (e) { /* si truena, mostramos el sitio igual sin esas secciones */ }

  render(perfil, Array.isArray(props) ? props : [], Array.isArray(testimonios) ? testimonios : []);
}

/* ── Render (una sola estructura semántica; la personalidad visual
   de cada plantilla vive en sitio.css vía [data-template]) ─────────────── */
function render(perfil, props, testimonios) {
  const redes = perfil.redes || {};
  const waPerfil = waLink(perfil.whatsapp_publico, 'Hola ' + (perfil.nombre_publico || '') + ', vi tu sitio en Broquer y me gustaría más información.');

  const heroHtml = `
    <section class="st-hero">
      <div class="st-hero__inner">
        <div class="st-hero__foto">
          ${perfil.foto_url ? `<img src="${esc(perfil.foto_url)}" alt="${esc(perfil.nombre_publico || '')}"/>` : `<span>${esc(iniciales(perfil.nombre_publico))}</span>`}
        </div>
        <div class="st-hero__texto">
          <h1>${esc(perfil.nombre_publico || 'Agente inmobiliario')}</h1>
          ${perfil.zona_cobertura ? `<div class="st-hero__zona">📍 ${esc(perfil.zona_cobertura)}</div>` : ''}
          ${perfil.bio ? `<p class="st-hero__bio">${esc(perfil.bio)}</p>` : ''}
          <div class="st-hero__meta">
            ${perfil.anos_experiencia ? `<span>${esc(String(perfil.anos_experiencia))} años de experiencia</span>` : ''}
            ${props.length ? `<span>${props.length} propiedad${props.length===1?'':'es'} disponible${props.length===1?'':'s'}</span>` : ''}
          </div>
          <div class="st-hero__acts">
            ${waPerfil ? `<a class="st-btn st-btn--primary" href="${waPerfil}" target="_blank" rel="noopener">Contactar por WhatsApp</a>` : ''}
            ${redSocialLink('instagram', redes.instagram) ? `<a class="st-social" href="${esc(redSocialLink('instagram', redes.instagram))}" target="_blank" rel="noopener" aria-label="Instagram">${ICONO_IG}</a>` : ''}
            ${redSocialLink('facebook', redes.facebook) ? `<a class="st-social" href="${esc(redSocialLink('facebook', redes.facebook))}" target="_blank" rel="noopener" aria-label="Facebook">${ICONO_FB}</a>` : ''}
            ${redSocialLink('tiktok', redes.tiktok) ? `<a class="st-social" href="${esc(redSocialLink('tiktok', redes.tiktok))}" target="_blank" rel="noopener" aria-label="TikTok">${ICONO_TT}</a>` : ''}
          </div>
        </div>
      </div>
    </section>
  `;

  const propsHtml = `
    <section class="st-props" id="propiedades">
      <h2>Propiedades disponibles</h2>
      ${props.length ? `<div class="st-grid">
        ${props.map((p, i) => tarjetaProp(p, i, perfil)).join('')}
      </div>` : `<div class="st-vacio">Por ahora no hay propiedades publicadas. Vuelve pronto.</div>`}
    </section>
  `;

  const testiHtml = testimonios.length ? `
    <section class="st-testis">
      <h2>Lo que dicen mis clientes</h2>
      <div class="st-testis__grid">
        ${testimonios.map(t => `<div class="st-testi">
          ${t.calificacion ? `<div class="st-testi__stars">${'★'.repeat(t.calificacion)}${'☆'.repeat(5 - t.calificacion)}</div>` : ''}
          <p class="st-testi__texto">“${esc(t.texto)}”</p>
          <div class="st-testi__nombre">${esc(t.nombre_cliente)}</div>
        </div>`).join('')}
      </div>
    </section>
  ` : '';

  const footerHtml = `
    <footer class="st-footer">
      <div>${esc(perfil.nombre_publico || '')}${perfil.whatsapp_publico ? ' · ' + esc(perfil.whatsapp_publico) : ''}</div>
      <a href="https://broquer.app" class="st-credito">Hecho con Broquer</a>
    </footer>
  `;

  const waFloat = waPerfil ? `<a class="st-wa-float" href="${waPerfil}" target="_blank" rel="noopener" aria-label="WhatsApp">${ICONO_WA}</a>` : '';

  document.getElementById('sitio-root').innerHTML = heroHtml + propsHtml + testiHtml + footerHtml + waFloat;

  document.querySelectorAll('.st-card').forEach(el => {
    el.addEventListener('click', () => toggleDetalleProp(el.dataset.idx));
  });
}

let _propsActuales = [];
function tarjetaProp(p, i, perfil) {
  _propsActuales[i] = p;
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
  const p = _propsActuales[idx];
  if (!p) return;
  const fotos = Array.isArray(p.fotos) && p.fotos.length ? p.fotos : [];
  const ubic = [p.colonia, p.ciudad].filter(Boolean).join(', ');
  const wa = waLink(document.body.dataset.whatsappActual, 'Hola, me interesa esta propiedad: ' + (p.titulo || '') + (ubic ? ' (' + ubic + ')' : ''));
  const overlay = document.createElement('div');
  overlay.className = 'st-modal-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  overlay.innerHTML = `<div class="st-modal">
    <button class="st-modal__x" onclick="this.closest('.st-modal-overlay').remove()">✕</button>
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
      ${wa ? `<a class="st-btn st-btn--primary" href="${wa}" target="_blank" rel="noopener">Preguntar por esta propiedad</a>` : ''}
    </div>
  </div>`;
  document.body.appendChild(overlay);
}

const ICONO_WA = '<svg width="26" height="26" viewBox="0 0 32 32" fill="currentColor"><path d="M16 0C7.163 0 0 7.163 0 16c0 2.823.736 5.474 2.029 7.776L0 32l8.42-2.207A15.9 15.9 0 0016 32c8.837 0 16-7.163 16-16S24.837 0 16 0zm7.45 19.2c-.39-.196-2.31-1.142-2.668-1.273-.358-.13-.618-.196-.878.196-.26.39-1.008 1.272-1.236 1.532-.228.26-.456.293-.846.098-.39-.196-1.65-.61-3.143-1.94-1.162-1.037-1.948-2.318-2.176-2.708-.228-.39-.024-.6.171-.795.176-.175.39-.456.586-.683.196-.228.26-.39.39-.65.13-.26.065-.488-.033-.683-.098-.196-.878-2.117-1.203-2.9-.317-.762-.64-.66-.879-.672-.227-.012-.487-.014-.747-.014-.26 0-.683.098-1.04.488-.358.39-1.366 1.336-1.366 3.257 0 1.92 1.398 3.778 1.594 4.038.195.26 2.752 4.203 6.667 5.893.93.402 1.657.642 2.223.821.934.297 1.785.255 2.457.155.75-.112 2.31-.945 2.636-1.857.325-.911.325-1.692.228-1.857-.098-.165-.358-.26-.748-.456z"/></svg>';
const ICONO_IG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg>';
const ICONO_FB = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M13.5 21v-8h2.7l.4-3.1h-3.1V8c0-.9.25-1.5 1.55-1.5H16.7V3.7C16.4 3.65 15.4 3.56 14.25 3.56c-2.4 0-4.05 1.47-4.05 4.16V9.9H7.5V13h2.7v8h3.3z"/></svg>';
const ICONO_TT = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 2c.3 2.1 1.7 3.7 3.8 3.9v2.6c-1.4.1-2.7-.3-3.8-1v6.6c0 3.2-2.6 5.7-5.7 5.7S5 16.3 5 13.1c0-3.1 2.4-5.6 5.5-5.7v2.7c-1.5.1-2.7 1.4-2.7 3 0 1.7 1.4 3 3 3s3.1-1.3 3.1-3V2h2.6z"/></svg>';

document.addEventListener('DOMContentLoaded', cargarSitio);
