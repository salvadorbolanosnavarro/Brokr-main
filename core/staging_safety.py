"""Opt-in staging outbound isolation. Production is untouched when unset.

Only the independent staging DB and test-mode Stripe can be contacted via
HTTPX. SMTP delivery is forbidden. Other integrations return a real failure,
never a fabricated successful delivery. These are the outbound clients used
by the current application; future clients require equivalent guards.
"""
import os
import smtplib
import imaplib
from urllib.parse import urlsplit
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

def install_staging_safety():
    global _installed
    if os.getenv('BROQUER_ENV','').lower() != 'staging' or _installed: return
    ref = validate(os.environ)
    allowed = {f'{ref}.supabase.co'}
    if os.getenv('STRIPE_SECRET_KEY'): allowed.add('api.stripe.com')
    original_async = httpx.AsyncClient.send
    original_sync = httpx.Client.send
    def check(request):
        if request.url.scheme != 'https' or request.url.host not in allowed:
            raise httpx.RequestError('External integration disabled in Broquer staging',request=request)
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
    def no_smtp(*args,**kwargs):
        raise smtplib.SMTPException('SMTP delivery disabled in Broquer staging')
    httpx.AsyncClient.send = send_async
    httpx.Client.send = send_sync
    smtplib.SMTP.connect = no_smtp
    smtplib.SMTP_SSL.connect = no_smtp
    def no_imap(*args,**kwargs):
        raise imaplib.IMAP4.error("IMAP disabled in Broquer staging")
    imaplib.IMAP4.open = no_imap
    imaplib.IMAP4_SSL.open = no_imap
    _installed = True
