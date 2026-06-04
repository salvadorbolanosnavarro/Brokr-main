// capacitor-bridge.js — puente nativo iOS para Broquer.
// No-op cuando se carga desde un navegador web normal.
// Solo se activa cuando window.Capacitor.isNativePlatform() === true (iOS app).
//
// NOTA (App Store review): en iOS NO se inyecta "Iniciar sesión con Apple"
// ni se muestran botones de OAuth de Google ni botones de pago/checkout.
// El login en iOS es exclusivamente correo + contraseña, y la suscripción
// se gestiona únicamente vía web (broquer.app). Esto se controla marcando
// <html class="is-ios-native"> lo antes posible para que el CSS y app-shell.js
// oculten esos elementos solo dentro del WebView nativo.
(function () {
  const isNative = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
  if (!isNative) return;

  // ─── 0. Marca el contexto nativo iOS cuanto antes ───────────────────
  // El CSS (.is-ios-native ...) y app-shell.js dependen de esta clase/flag
  // para ocultar OAuth de Google y cualquier botón de pago dentro de la app.
  try {
    document.documentElement.classList.add('is-ios-native');
    window.__BROQUER_IOS_NATIVE__ = true;
  } catch (_) {}

  const SB_URL = 'https://urtgysmtnvoqaljuhntz.supabase.co';
  const SB_KEY = 'sb_publishable_EVGLfmHVorBpQQWAh-vypA_hANNk_-i';

  // ─── 1. Desregistrar service worker (rompe caching en WebView) ───
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations()
      .then(rs => rs.forEach(r => r.unregister()))
      .catch(() => {});
  }

  // ─── 2. Push notifications (APNs) ─────────────────────────────────
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
  // Después de que el shell autentica y carga, registramos APNs.
  window.addEventListener('brokr-shell-ready', registerPush);

  // Exponer para debug
  window.brokrCapacitor = { registerPush };
})();
