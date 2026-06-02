// capacitor-bridge.js — puente nativo iOS para Brokr.
// No-op cuando se carga desde un navegador web normal.
// Solo se activa cuando window.Capacitor.isNativePlatform() === true (iOS app).
(function () {
  const isNative = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
  if (!isNative) return;

  const SB_URL = 'https://urtgysmtnvoqaljuhntz.supabase.co';
  const SB_KEY = 'sb_publishable_EVGLfmHVorBpQQWAh-vypA_hANNk_-i';
  const APPLE_CLIENT_ID = 'com.broquer.app';

  // ─── 1. Desregistrar service worker (rompe caching en WebView) ───
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations()
      .then(rs => rs.forEach(r => r.unregister()))
      .catch(() => {});
  }

  // ─── 2. Sign in with Apple (requerido por Apple guideline 4.8) ───
  function nonce16() {
    const a = new Uint8Array(16);
    crypto.getRandomValues(a);
    return Array.from(a).map(b => b.toString(16).padStart(2, '0')).join('');
  }

  async function signInWithApple() {
    const { SignInWithApple } = window.Capacitor.Plugins;
    if (!SignInWithApple) throw new Error('Plugin SignInWithApple no disponible');
    const res = await SignInWithApple.authorize({
      clientId: APPLE_CLIENT_ID,
      redirectURI: SB_URL + '/auth/v1/callback',
      scopes: 'email name',
      nonce: nonce16(),
    });
    const idToken = res && res.response && res.response.identityToken;
    if (!idToken) throw new Error('Apple no devolvió identityToken');

    const r = await fetch(SB_URL + '/auth/v1/token?grant_type=id_token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'apikey': SB_KEY },
      body: JSON.stringify({ provider: 'apple', id_token: idToken }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || !data.access_token) {
      throw new Error(data.error_description || data.msg || 'apple-signin-failed');
    }
    localStorage.setItem('sb_token', data.access_token);
    if (data.refresh_token) localStorage.setItem('sb_refresh', data.refresh_token);
    if (data.user) localStorage.setItem('sb_user', JSON.stringify(data.user));
    window.location.href = 'index.html';
  }

  function injectAppleButton() {
    const googles = document.querySelectorAll('button[onclick*="doGoogle"]');
    googles.forEach(g => {
      if (g.parentNode.querySelector('[data-brokr-apple]')) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.dataset.brokrApple = '1';
      btn.className = g.className;
      btn.style.marginTop = '10px';
      btn.innerHTML =
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="margin-right:8px;vertical-align:middle">' +
        '<path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/>' +
        '</svg>Continuar con Apple';
      btn.addEventListener('click', () => {
        btn.disabled = true;
        signInWithApple().catch(err => {
          console.error('[apple-signin]', err);
          alert('No se pudo iniciar sesión con Apple: ' + (err.message || err));
          btn.disabled = false;
        });
      });
      g.parentNode.insertBefore(btn, g.nextSibling);
    });
  }

  // ─── 3. Push notifications (APNs) ─────────────────────────────────
  async function registerPush() {
    try {
      const { PushNotifications } = window.Capacitor.Plugins;
      if (!PushNotifications) return;
      const perm = await PushNotifications.requestPermissions();
      if (perm.receive !== 'granted') return;
      await PushNotifications.register();

      PushNotifications.addListener('registration', t => {
        const tok = localStorage.getItem('sb_token');
        if (!tok) return;
        // Guarda el APNs token en la fila del usuario actual (Supabase RLS lo limita a su propio id)
        fetch(SB_URL + '/rest/v1/usuarios?select=id', {
          method: 'PATCH',
          headers: {
            'apikey': SB_KEY,
            'Authorization': 'Bearer ' + tok,
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal',
          },
          body: JSON.stringify({ apns_token: t.value }),
        }).catch(() => {});
      });
      PushNotifications.addListener('registrationError', e => console.error('[push] regError', e));
    } catch (e) {
      console.error('[push] init', e);
    }
  }

  // ─── Lifecycle ────────────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectAppleButton);
  } else {
    injectAppleButton();
  }
  // Login.html re-renderiza forms (tab login/signup); reintenta inyectar.
  try {
    new MutationObserver(() => injectAppleButton())
      .observe(document.body || document.documentElement, { childList: true, subtree: true });
  } catch (_) {}

  // Después de que el shell autentica y carga, registramos APNs.
  window.addEventListener('brokr-shell-ready', registerPush);

  // Exponer para debug
  window.brokrCapacitor = { signInWithApple, registerPush };
})();
