"""Opt-in staging outbound isolation. Production is untouched when unset.

Allowed over HTTPX: the independent staging DB, test-mode Stripe, AI and data
providers, and delivery providers ONLY for addresses/numbers listed in
BROQUER_STAGING_TEST_PHONES and BROQUER_STAGING_TEST_EMAILS. Anything else
returns a real failure, never a fabricated successful delivery. Facebook ad
spend and page publishing stay blocked here.
"""
import json
import os
import re
import smtplib
import httpx

PROD_REF = 'urtgysmtnvoqaljuhntz'
_installed = False

def validate(env):
    db = env.get('SUPABASE_URL','').rstrip('/')
    ref = env.get('BROQUER_STAGING_DB_REF','').strip()
    if not ref or ref == PROD_REF or db != f'https://{ref}.supabase.co':
        raise RuntimeError('Staging requires a separate explicitly approved Supabase reference.')
    if env.get('BROQUER_STAGING_PROJECT_NAME','').strip() != 'broquer-redesign-staging':
        raise RuntimeError('Use broquer-redesign-staging, never broquer-beta.')
    for flag in ('RECORDATORIOS_ACTIVOS','BUSCADOR_PROPIEDADES_ACTIVO'):
        if env.get(flag,'').lower() != 'false':
            raise RuntimeError(f'{flag} must be false in staging.')
    for name in ('APP_URL','FRONTEND_URL'):
        if env.get(name,'').rstrip('/') != 'https://staging.broquer.app':
            raise RuntimeError(f'{name} must target the existing staging frontend.')
    for name in ('API_BASE_URL','BROQUER_API_BASE'):
        if env.get(name,'').rstrip('/') != 'https://brokr-main-staging.up.railway.app':
            raise RuntimeError(f'{name} must target the existing staging API.')
    stripe = env.get('STRIPE_SECRET_KEY','')
    if stripe and not stripe.startswith(('sk_test_','rk_test_')):
        raise RuntimeError('Staging only accepts test-mode Stripe credentials.')
    return ref

_READ_ONLY_PROVIDERS = {
    'api.anthropic.com','api.groq.com','generativelanguage.googleapis.com','api.firecrawl.dev',
    'api.tavily.com','api.search.brave.com','serpapi.com','www.googleapis.com','maps.googleapis.com',
    'places.googleapis.com','www.banxico.org.mx','api.easybroker.com',
}
_GRAPH_SETUP_PATHS = ('/register','/subscribed_apps','/message_templates','/media')

def _digits_set(raw):
    return {re.sub(r'\D','',x)[-10:] for x in raw.split(',') if re.sub(r'\D','',x)}

def _emails_set(raw):
    return {x.strip().lower() for x in raw.split(',') if x.strip()}

def _body(request):
    try:
        return json.loads(request.content or b'{}')
    except Exception:
        return {}

def _check_graph(request, test_phones):
    path = request.url.path.rstrip('/')
    if path.endswith('/messages'):
        to = re.sub(r'\D','',str(_body(request).get('to') or request.url.params.get('to') or ''))[-10:]
        if not to or to not in test_phones:
            raise httpx.RequestError('WhatsApp in staging only reaches BROQUER_STAGING_TEST_PHONES',request=request)
        return
    if not path.endswith(_GRAPH_SETUP_PATHS):
        raise httpx.RequestError('Facebook writes other than test WhatsApp are disabled in staging',request=request)

def _check_resend(request, test_emails):
    to = _body(request).get('to') or []
    to = [to] if isinstance(to,str) else list(to)
    extra = (_body(request).get('cc') or []) + (_body(request).get('bcc') or []) if isinstance(_body(request).get('cc') or [],list) and isinstance(_body(request).get('bcc') or [],list) else ['invalid']
    recipients = {re.sub(r'.*<|>.*','',str(x)).strip().lower() for x in [*to,*extra]}
    if not recipients or not recipients <= test_emails:
        raise httpx.RequestError('Email in staging only reaches BROQUER_STAGING_TEST_EMAILS',request=request)

def install_staging_safety():
    global _installed
    if os.getenv('BROQUER_ENV','').lower() != 'staging' or _installed: return
    ref = validate(os.environ)
    allowed = {f'{ref}.supabase.co'}
    if os.getenv('STRIPE_SECRET_KEY'): allowed.add('api.stripe.com')
    allowed |= _READ_ONLY_PROVIDERS | {'graph.facebook.com','api.resend.com','api.sandbox.push.apple.com'}
    test_phones = _digits_set(os.getenv('BROQUER_STAGING_TEST_PHONES',''))
    test_emails = _emails_set(os.getenv('BROQUER_STAGING_TEST_EMAILS',''))
    original_async = httpx.AsyncClient.send
    original_sync = httpx.Client.send
    def check(request):
        if request.url.scheme != 'https' or request.url.host not in allowed:
            raise httpx.RequestError('External integration disabled in Broquer staging',request=request)
        if request.url.host == 'graph.facebook.com' and request.method != 'GET':
            _check_graph(request, test_phones)
        if request.url.host == 'api.resend.com':
            _check_resend(request, test_emails)
        if request.url.host == 'api.stripe.com':
            # Prevent per-user credentials from bypassing the test key configured above.
            auth = request.headers.get('authorization','')
            if auth.lower().startswith('basic '):
                import base64
                try: auth = base64.b64decode(auth[6:]).decode()
                except Exception: auth = ''
            if not any(v in auth for v in ('sk_test_','rk_test_')):
                raise httpx.RequestError('Only Stripe test requests are allowed',request=request)
    async def send_async(self,request,*args,**kwargs):
        check(request)
        kwargs["follow_redirects"] = False
        return await original_async(self,request,*args,**kwargs)
    def send_sync(self,request,*args,**kwargs):
        check(request)
        kwargs["follow_redirects"] = False
        return original_sync(self,request,*args,**kwargs)
    original_sendmail = smtplib.SMTP.sendmail
    def guarded_sendmail(self,from_addr,to_addrs,*args,**kwargs):
        to_list = [to_addrs] if isinstance(to_addrs,str) else list(to_addrs)
        if not to_list or not {str(x).strip().lower() for x in to_list} <= test_emails:
            raise smtplib.SMTPException('SMTP in staging only reaches BROQUER_STAGING_TEST_EMAILS')
        return original_sendmail(self,from_addr,to_addrs,*args,**kwargs)
    httpx.AsyncClient.send = send_async
    httpx.Client.send = send_sync
    smtplib.SMTP.sendmail = guarded_sendmail
    _installed = True
