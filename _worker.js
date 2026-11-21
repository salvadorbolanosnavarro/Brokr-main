// Staging-preview only. Pages' existing root deployment must never expose the
// repository source. Route exclusively to the audited prebuilt public artifact.
import manifest from './preview-public-manifest.json';
import {pilotRequest} from './scripts/staging_pilot_worker.js';
const API = 'https://brokr-main-staging.up.railway.app';
const DB = 'https://tymhlvawnqadqgwnpruk.supabase.co';
const CSP = `connect-src 'self' ${API} ${DB} wss://tymhlvawnqadqgwnpruk.supabase.co https://o4511509854945280.ingest.us.sentry.io; object-src 'none'; base-uri 'self'`;
const headers = {'Content-Security-Policy':CSP,'X-Robots-Tag':'noindex, nofollow','X-Cecil-Preview':'staging-only','Cache-Control':'no-store'};
export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);
      if (!url.hostname.endsWith('.broquer-staging.pages.dev') && url.hostname !== 'broquer-staging.pages.dev')
        return new Response('Staging preview only',{status:503,headers});
      const pilot=await pilotRequest(request);
      if(pilot){for(const [key,value] of Object.entries(headers))pilot.headers.set(key,value);pilot.headers.set('Cache-Control','private, no-store');return pilot;}
      if (!['GET','HEAD'].includes(request.method)) return new Response('Method not allowed',{status:405,headers});
      let path;
      try { path=decodeURIComponent(url.pathname); } catch (_) { return new Response('Invalid path',{status:400,headers}); }
      if (path.includes('..') || path.includes('\\') || path.includes('\0')) return new Response('Invalid path',{status:400,headers});
      let name=path.replace(/^\//,'');
      if (!name || name.endsWith('/')) name+='index.html';
      if (!Object.hasOwn(manifest,name) && !name.split('/').pop().includes('.')) name+='.html';
      if (!Object.hasOwn(manifest,name)) return new Response('Not found',{status:404,headers});
      // Gate alternate HTML on a server-verified staging identity and flag.
      // The cookie is HttpOnly; it never replaces/removes the app's auth session.
      if(name.startsWith('cecil/')&&name.endsWith('.html')){
        const token=(request.headers.get('Cookie')||'').split(';').map(v=>v.trim()).find(v=>v.startsWith('cecil_staging_session='))?.slice(22);
        const check=new Request(url.origin+'/ui/cecil',{headers:token?{Authorization:'Bearer '+token}:{}});
        const state=await pilotRequest(check);
        const enabled=state?.ok&&(await state.json()).enabled===true;
        if(!enabled){const dest=new URL(url);dest.pathname='/'+name.slice(6);return new Response(null,{status:302,headers:{...headers,Location:dest.href}});}
      }
      // Pages resolves clean HTML URLs; requesting .html internally can redirect.
      let assetName=name;
      if (assetName.endsWith('index.html')) assetName=assetName.slice(0,-10);
      else if (assetName.endsWith('.html')) assetName=assetName.slice(0,-5);
      url.pathname='/preview-public/'+assetName;
      const asset=await env.ASSETS.fetch(new Request(url,request));
      if (asset.status>=300 && asset.status<400) return new Response('Unexpected asset redirect',{status:502,headers});
      const response=new Response(asset.body,asset);
      for (const [key,value] of Object.entries(headers)) response.headers.set(key,value);
      return response;
    } catch (_) {
      return new Response('Preview temporarily unavailable',{status:503,headers});
    }
  }
};
