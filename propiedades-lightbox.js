// propiedades-lightbox.js — carrusel de fotos a pantalla completa
// (listado y ficha de Inmuebles) con zoom propio: pellizco, doble toque,
// arrastre y deslizar para cambiar de foto. Se separó de propiedades.html
// para no inflarlo. Usa g() de propiedades.html.

// ── Lightbox: carrusel de fotos a pantalla completa ────────────────
let LB_FOTOS = [];
let LB_IDX = 0;

function openLightbox(fotosJsonEncoded, startIdx) {
  try {
    const fotos = JSON.parse(decodeURIComponent(fotosJsonEncoded));
    if (!fotos.length) return;
    LB_FOTOS = fotos;
    LB_IDX = Math.max(0, Math.min(startIdx, fotos.length - 1));
    lightboxRender();
    g('lightbox-overlay').classList.add('is-open');
  } catch(e) {}
}

function lightboxRender() {
  lbZoomReset(false);
  g('lightbox-img').src = LB_FOTOS[LB_IDX] || '';
  const varias = LB_FOTOS.length > 1;
  g('lightbox-counter').textContent = (LB_IDX + 1) + ' / ' + LB_FOTOS.length;
  g('lightbox-counter').style.display = varias ? '' : 'none';
  g('lightbox-prev').style.display = varias ? '' : 'none';
  g('lightbox-next').style.display = varias ? '' : 'none';
}

function lightboxNav(delta) {
  if (!LB_FOTOS.length) return;
  LB_IDX = (LB_IDX + delta + LB_FOTOS.length) % LB_FOTOS.length;
  lightboxRender();
}

function closeLightbox() {
  lbZoomReset(false);
  g('lightbox-overlay').classList.remove('is-open');
}

/* ── Zoom de la foto dentro del lightbox ───────────────────────────
   Pellizco o doble toque para ampliar, arrastrar para moverse por la
   foto ampliada y deslizar a los lados para cambiar de foto cuando no
   hay zoom. En escritorio: rueda del mouse o doble clic. Todo ocurre
   sobre la imagen (transform), nunca sobre la página. */
const LB_ZOOM_MAX = 4;
const LB_ZOOM_DOBLE = 2.5;
let lbZ = { s: 1, x: 0, y: 0 };
let lbGesto = null;
let lbUltimoTap = 0;
let lbArrastro = false;

function lbImg() { return g('lightbox-img'); }

function lbAplicar(animar) {
  const img = lbImg();
  if (!img) return;
  img.classList.toggle('is-animating', !!animar);
  img.classList.toggle('is-zoomed', lbZ.s > 1.01);
  img.style.transform = lbZ.s > 1.001 || lbZ.x || lbZ.y
    ? `translate(${lbZ.x}px, ${lbZ.y}px) scale(${lbZ.s})` : '';
}

function lbLimitar() {
  const img = lbImg();
  if (!img) return;
  lbZ.s = Math.max(1, Math.min(LB_ZOOM_MAX, lbZ.s));
  if (lbZ.s <= 1.001) { lbZ.s = 1; lbZ.x = 0; lbZ.y = 0; return; }
  // Sin transform, offsetWidth/Height son el tamaño base de la foto.
  const w = img.offsetWidth, h = img.offsetHeight;
  const maxX = Math.max(0, (w * lbZ.s - window.innerWidth) / 2);
  const maxY = Math.max(0, (h * lbZ.s - window.innerHeight) / 2);
  lbZ.x = Math.max(-maxX, Math.min(maxX, lbZ.x));
  lbZ.y = Math.max(-maxY, Math.min(maxY, lbZ.y));
}

function lbZoomReset(animar) {
  lbZ = { s: 1, x: 0, y: 0 };
  lbGesto = null;
  lbAplicar(animar);
}

// Amplía hacia el punto (cx, cy) de la pantalla para que lo que está bajo
// los dedos (o el cursor) se quede en su lugar.
function lbZoomEn(nuevaS, cx, cy, animar) {
  const img = lbImg();
  if (!img) return;
  // Centro de la foto sin transformar (está centrada en su contenedor)
  // más el desplazamiento actual.
  const r = img.parentElement.getBoundingClientRect();
  const ox = r.left + r.width / 2 + lbZ.x, oy = r.top + r.height / 2 + lbZ.y;
  const s0 = lbZ.s;
  nuevaS = Math.max(1, Math.min(LB_ZOOM_MAX, nuevaS));
  const k = nuevaS / s0;
  lbZ.x += (cx - ox) * (1 - k);
  lbZ.y += (cy - oy) * (1 - k);
  lbZ.s = nuevaS;
  lbLimitar();
  lbAplicar(animar);
}

function lbDist(t) { return Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY); }
function lbCentro(t) { return { x: (t[0].clientX + t[1].clientX) / 2, y: (t[0].clientY + t[1].clientY) / 2 }; }

(function lbGestos() {
  const ov = g('lightbox-overlay');
  if (!ov) return;

  ov.addEventListener('touchstart', (e) => {
    if (e.target.closest('button')) return;
    const t = e.touches;
    if (t.length === 2) {
      const c = lbCentro(t);
      lbGesto = { tipo: 'pinch', d0: lbDist(t), s0: lbZ.s, cx: c.x, cy: c.y };
    } else if (t.length === 1) {
      lbGesto = { tipo: 'pan', x0: t[0].clientX, y0: t[0].clientY, zx: lbZ.x, zy: lbZ.y, movio: false };
    }
    lbAplicar(false);
  }, { passive: true });

  ov.addEventListener('touchmove', (e) => {
    if (!lbGesto) return;
    e.preventDefault();
    const t = e.touches;
    if (lbGesto.tipo === 'pinch' && t.length === 2) {
      const c = lbCentro(t);
      const objetivo = lbGesto.s0 * lbDist(t) / lbGesto.d0;
      // Desplazamiento del centro del pellizco = arrastre simultáneo.
      lbZ.x += c.x - lbGesto.cx; lbZ.y += c.y - lbGesto.cy;
      lbGesto.cx = c.x; lbGesto.cy = c.y;
      lbZoomEn(objetivo, c.x, c.y, false);
    } else if (lbGesto.tipo === 'pan' && t.length === 1) {
      const dx = t[0].clientX - lbGesto.x0, dy = t[0].clientY - lbGesto.y0;
      if (Math.abs(dx) > 6 || Math.abs(dy) > 6) lbGesto.movio = true;
      if (lbZ.s > 1.01) {
        lbZ.x = lbGesto.zx + dx; lbZ.y = lbGesto.zy + dy;
        lbLimitar();
        lbAplicar(false);
      }
    }
  }, { passive: false });

  ov.addEventListener('touchend', (e) => {
    if (!lbGesto) return;
    const gesto = lbGesto;
    if (gesto.tipo === 'pinch') {
      // Al soltar un dedo del pellizco se sigue con arrastre del que queda.
      if (e.touches.length === 1) {
        lbGesto = { tipo: 'pan', x0: e.touches[0].clientX, y0: e.touches[0].clientY, zx: lbZ.x, zy: lbZ.y, movio: true };
      } else lbGesto = null;
      if (lbZ.s < 1.05) lbZoomReset(true);
      return;
    }
    if (e.touches.length) return;
    lbGesto = null;
    const ch = e.changedTouches[0];
    const dx = ch.clientX - gesto.x0, dy = ch.clientY - gesto.y0;
    if (!gesto.movio) {
      const ahora = Date.now();
      if (ahora - lbUltimoTap < 300) {
        lbUltimoTap = 0;
        if (lbZ.s > 1.01) lbZoomReset(true);
        else lbZoomEn(LB_ZOOM_DOBLE, ch.clientX, ch.clientY, true);
        e.preventDefault(); // evita el click fantasma que cerraría el lightbox
      } else {
        lbUltimoTap = ahora;
      }
      return;
    }
    // Sin zoom: deslizar para cambiar de foto o hacia abajo para cerrar.
    if (lbZ.s <= 1.01) {
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) lightboxNav(dx < 0 ? 1 : -1);
      else if (dy > 90 && Math.abs(dy) > Math.abs(dx)) closeLightbox();
    }
  }, { passive: false });

  ov.addEventListener('touchcancel', () => { lbGesto = null; if (lbZ.s < 1.05) lbZoomReset(true); });

  // Terminar de arrastrar la foto con el mouse sobre el fondo no debe cerrar.
  ov.addEventListener('click', (e) => { if (lbArrastro) e.stopPropagation(); }, true);

  // Escritorio: rueda para ampliar, doble clic para alternar, arrastrar para moverse.
  ov.addEventListener('wheel', (e) => {
    if (!ov.classList.contains('is-open')) return;
    e.preventDefault();
    const factor = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0025));
    lbZoomEn(lbZ.s * factor, e.clientX, e.clientY, false);
  }, { passive: false });

  const img = lbImg();
  img.addEventListener('dblclick', (e) => {
    e.preventDefault();
    if (lbZ.s > 1.01) lbZoomReset(true);
    else lbZoomEn(LB_ZOOM_DOBLE, e.clientX, e.clientY, true);
  });
  img.addEventListener('mousedown', (e) => {
    if (e.button !== 0 || lbZ.s <= 1.01) return;
    e.preventDefault();
    const x0 = e.clientX, y0 = e.clientY, zx = lbZ.x, zy = lbZ.y;
    lbArrastro = false;
    const mover = (ev) => {
      if (Math.abs(ev.clientX - x0) > 3 || Math.abs(ev.clientY - y0) > 3) lbArrastro = true;
      lbZ.x = zx + ev.clientX - x0; lbZ.y = zy + ev.clientY - y0;
      lbLimitar(); lbAplicar(false);
    };
    const soltar = () => {
      document.removeEventListener('mousemove', mover);
      document.removeEventListener('mouseup', soltar);
      setTimeout(() => { lbArrastro = false; }, 0);
    };
    document.addEventListener('mousemove', mover);
    document.addEventListener('mouseup', soltar);
  });

  // Al girar el teléfono o cambiar el tamaño, la foto vuelve a encajar.
  window.addEventListener('resize', () => { if (lbZ.s > 1.01) { lbLimitar(); lbAplicar(false); } });
})();

document.addEventListener('keydown', (e) => {
  if (!g('lightbox-overlay').classList.contains('is-open')) return;
  if (e.key === 'Escape') closeLightbox();
  else if (e.key === 'ArrowLeft') lightboxNav(-1);
  else if (e.key === 'ArrowRight') lightboxNav(1);
});
