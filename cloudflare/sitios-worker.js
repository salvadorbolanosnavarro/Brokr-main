// cloudflare/sitios-worker.js · Worker para los dominios propios de los sitios
// (Cloudflare for SaaS). Cada dominio de cliente (www.inmobiliaria.mx) llega
// aquí por el "fallback origin" sitios.broquer.app; el Worker reenvía la
// petición al backend de Broquer diciéndole qué dominio pidió el visitante.
//
// Variables del Worker (Settings → Variables):
//   BACKEND       https://api.broquer.app   (o el de staging)
//   SITIOS_CLAVE  la misma clave que SITIOS_WORKER_CLAVE en Railway (secreto)
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const destino = new URL(url.pathname + url.search, env.BACKEND || 'https://api.broquer.app');
    const headers = new Headers(request.headers);
    headers.set('X-Sitio-Host', url.hostname);
    headers.set('X-Sitio-Clave', env.SITIOS_CLAVE || '');
    headers.set('X-Forwarded-Host', url.hostname);
    const resp = await fetch(destino.toString(), {
      method: request.method,
      headers,
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
      redirect: 'manual',
    });
    // Las redirecciones del backend (formulario enviado) apuntan a rutas
    // relativas; si vienen absolutas al backend, se reescriben al dominio.
    const loc = resp.headers.get('location');
    if (loc && loc.startsWith(destino.origin)) {
      const h = new Headers(resp.headers);
      h.set('location', loc.replace(destino.origin, url.origin));
      return new Response(resp.body, { status: resp.status, headers: h });
    }
    return resp;
  },
};
