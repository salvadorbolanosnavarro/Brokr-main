/* ═══════════════════════════════════════════════════════════
   BROKR® — Servicios compartidos
   ═══════════════════════════════════════════════════════════
   Este archivo contiene TODA la lógica compartida:
   - Autenticación (Supabase)
   - Permisos
   - Utilidades de formato
   - Notificaciones
   
   Ningún módulo necesita repetir estas funciones.
   ═══════════════════════════════════════════════════════════ */

// ── CONFIG SUPABASE ──
const SB_URL = 'https://urtgysmtnvoqaljuhntz.supabase.co';
const SB_KEY = 'sb_publishable_EVGLfmHVorBpQQWAh-vypA_hANNk_-i';

// ── ESTADO GLOBAL ──
let currentUser = null;
let userProfile = null;

// ── AUTH ──
async function authInit() {
  const token = sessionStorage.getItem('sb_token');
  if (!token) { window.location.href = 'login.html'; return; }

  const user = JSON.parse(sessionStorage.getItem('sb_user') || '{}');
  if (!user.id) { window.location.href = 'login.html'; return; }

  try {
    const r = await fetch(`${SB_URL}/rest/v1/usuarios?id=eq.${user.id}&select=*`, {
      headers: { 'apikey': SB_KEY, 'Authorization': `Bearer ${token}` }
    });
    const data = await r.json();
    if (!data.length || data[0].activo === false) {
      sessionStorage.clear();
      window.location.href = 'login.html';
      return;
    }
    userProfile = data[0];
    currentUser = user;
  } catch (e) {
    console.warn('Auth error:', e);
    // Permitir acceso en error de red para no bloquear
    userProfile = {
      plan: 'pro',
      modulos: ['chat', 'isr', 'ficha-manual', 'ficha', 'contratos', 'avm'],
      activo: true
    };
  }
}

function logout() {
  sessionStorage.clear();
  window.location.href = 'login.html';
}

// ── PERMISOS ──
function hasModule(mod) {
  if (!userProfile) return false;
  if (userProfile.plan === 'admin' || userProfile.plan === 'pro') return true;
  return (userProfile.modulos || []).includes(mod);
}

function applyUserPermissions() {
  if (!userProfile) return;

  // Ocultar botones de módulos no disponibles
  document.querySelectorAll('.sb-btn[data-module]').forEach(btn => {
    const mod = btn.getAttribute('data-module');
    if (mod && !hasModule(mod)) {
      btn.style.display = 'none';
    }
  });

  // Ocultar tarjetas de módulos no disponibles en el dashboard
  document.querySelectorAll('.mod-card[data-module]').forEach(card => {
    const mod = card.getAttribute('data-module');
    if (mod && !hasModule(mod)) {
      card.style.display = 'none';
    }
  });

  // Mostrar enlace admin si corresponde
  if (userProfile.plan === 'admin') {
    const adminBtn = document.getElementById('admin-link-btn');
    if (adminBtn) adminBtn.style.display = 'flex';
  }
}

function updateUserDisplay() {
  if (!userProfile) return;
  const nameEl  = document.getElementById('user-name-display');
  const planEl  = document.getElementById('user-plan-display');
  const avatarEl = document.getElementById('user-avatar');
  
  const planLabels = { free: 'Free', modulos: 'Módulos', pro: 'Pro', admin: 'Admin' };
  
  if (nameEl) nameEl.textContent = userProfile.nombre || currentUser?.email || '—';
  if (planEl) planEl.textContent = planLabels[userProfile.plan] || userProfile.plan;
  if (avatarEl) avatarEl.textContent = (userProfile.nombre || '?')[0].toUpperCase();
}

// ── SUPABASE FETCH (genérico) ──
async function sbFetch(path, method = 'GET', body = null) {
  const token = sessionStorage.getItem('sb_token') || SB_KEY;
  const opts = {
    method,
    headers: {
      'apikey': SB_KEY,
      'Authorization': 'Bearer ' + token,
      'Content-Type': 'application/json',
      'Prefer': 'return=representation',
    }
  };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(SB_URL + '/rest/v1/' + path, opts);
  if (!r.ok) {
    const e = await r.text();
    throw new Error(e);
  }
  const txt = await r.text();
  return txt ? JSON.parse(txt) : [];
}

// ── FORMATEO DE DINERO ──
function getRawNum(val) {
  return parseFloat((val || '').replace(/[$,]/g, '').trim()) || 0;
}

function fmtMoney(n) {
  return '$' + Math.round(n).toLocaleString('es-MX');
}

function fmtMoneyInput(input) {
  const raw = getRawNum(input.value);
  if (!raw) { input.value = ''; return; }
  input.value = '$' + raw.toLocaleString('es-MX', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  });
}

function fmtPrecio(p, moneda = 'MXN') {
  if (!p) return '—';
  return (moneda === 'USD' ? 'USD ' : '$') +
    Number(p).toLocaleString('es-MX', { minimumFractionDigits: 0 });
}

function fmtPct(n) {
  return n.toFixed(2) + '%';
}

// ── NOTIFICACIONES PWA ──
function requestNotificationPermission() {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'default') {
    Notification.requestPermission();
  }
}

function notifyUser(title, body, url) {
  if (!('Notification' in window)) return;
  if (Notification.permission !== 'granted') {
    Notification.requestPermission().then(p => {
      if (p === 'granted') _doNotify(title, body, url);
    });
    return;
  }
  _doNotify(title, body, url);
}

function _doNotify(title, body, url) {
  if (window._swReg) {
    window._swReg.showNotification(title, {
      body,
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      vibrate: [200, 100, 200],
      data: { url: url || '/' }
    });
  } else {
    new Notification(title, { body, icon: '/icon-192.png' });
  }
}

// ── SERVICE WORKER ──
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js?v=202603252200')
    .then(reg => {
      console.log('SW registrado:', reg.scope);
      window._swReg = reg;
    })
    .catch(err => console.warn('SW error:', err));
}

// Pedir permiso de notificaciones en primer gesto
document.addEventListener('click', () => requestNotificationPermission(), { once: true });

// ── HELPER: elemento por ID ──
function g(id) { return document.getElementById(id); }
