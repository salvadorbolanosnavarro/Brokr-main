"""Meaningful isolation checks; no production network or keys involved."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))  # core.side_effects is imported lazily
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
build=module('stagebuild','scripts/build_staging.py')
safety=module('stagesafety','core/staging_safety.py')
ENV={'BROQUER_STAGING_API_URL':'https://brokr-main-staging.up.railway.app','BROQUER_STAGING_SUPABASE_URL':'https://qaexample.supabase.co','BROQUER_STAGING_SUPABASE_KEY':'sb_publishable_testfixture','BROQUER_ENV':'staging','SUPABASE_URL':'https://qaexample.supabase.co','BROQUER_STAGING_DB_REF':'qaexample','BROQUER_STAGING_PROJECT_NAME':'broquer-redesign-staging','APP_URL':'https://staging.broquer.app','FRONTEND_URL':'https://staging.broquer.app','API_BASE_URL':'https://brokr-main-staging.up.railway.app','BROQUER_API_BASE':'https://brokr-main-staging.up.railway.app','RECORDATORIOS_ACTIVOS':'false','BUSCADOR_PROPIEDADES_ACTIVO':'false','STRIPE_SECRET_KEY':'sk_test_fixture'}
class Isolation(unittest.TestCase):
    def test_rejects_production_and_secret(self):
        for change in ({'CF_PAGES_BRANCH':'main'},{'BROQUER_STAGING_API_URL':'https://api.broquer.app'},{'BROQUER_STAGING_SUPABASE_URL':build.PROD_DB},{'BROQUER_STAGING_SUPABASE_KEY':'sb_secret_fixture'}):
            with self.assertRaises(ValueError):build.config(ENV|change)
    def test_build_public_only_and_rewrites(self):
        with tempfile.TemporaryDirectory() as d,patch.object(build,'ROOT',Path(d)):
            p=Path(d);(p/'styles').mkdir();(p/'styles/mobile-inputs.css').write_text('input{font-size:16px}')
            (p/'index.html').write_text('<head></head>'+build.PROD_DB+' https://api.broquer.app '+build.PROD_KEY)
            with patch.object(build.subprocess,'check_output',return_value='index.html\nstyles/mobile-inputs.css\nmain.py\nschema.sql\n.env\n'):
                build.build(ENV)
            output=(p/'dist/index.html').read_text()
            self.assertNotIn('api.broquer.app',output);self.assertNotIn(build.PROD_DB,output)
            self.assertIn('mobile-inputs.css',output)
            self.assertEqual(sorted(x.name for x in (p/'dist').iterdir()),['_headers','index.html','staging-auth-guard.js','styles'])
    def test_backend_configuration(self):
        self.assertEqual(safety.validate(ENV),'qaexample')
        for change in ({'RECORDATORIOS_ACTIVOS':'true'},{'BROQUER_STAGING_PROJECT_NAME':'broquer-beta'},{'SUPABASE_URL':build.PROD_DB}):
            with self.assertRaises(RuntimeError):safety.validate(ENV|change)
        # Since #218 a live Stripe key no longer aborts startup; every Stripe use
        # returns a controlled 503 without contacting Stripe (core/side_effects).
        from fastapi import HTTPException
        from core import side_effects
        with patch.dict(safety.os.environ,ENV|{'STRIPE_SECRET_KEY':'sk_live_fixture'},clear=True):
            with self.assertRaises(HTTPException) as blocked:side_effects.require_staging_stripe_key()
            self.assertEqual(blocked.exception.status_code,503)
            self.assertEqual(blocked.exception.detail['code'],'STAGING_STRIPE_TEST_KEY_REQUIRED')
    def test_inherited_production_credentials_are_dropped(self):
        import httpx,smtplib
        env=ENV|{'STRIPE_SECRET_KEY':'sk_live_fixture','STRIPE_WEBHOOK_SECRET':'whsec_fixture','WHATSAPP_TOKEN':'x','INSTAGRAM_TOKEN':'y'}
        from fastapi import HTTPException
        with patch.dict(safety.os.environ,env,clear=True),patch.object(httpx.Client,'send'),patch.object(httpx.AsyncClient,'send'),patch.object(smtplib.SMTP,'sendmail'):
            try:
                safety.install_staging_safety()
                for name in ('WHATSAPP_TOKEN','INSTAGRAM_TOKEN'):
                    self.assertNotIn(name,safety.os.environ)
                # The inherited live key stays in the environment (#218) but can
                # never reach Stripe: both the configured and a per-request key
                # are rejected before any network call.
                for headers in ({},{'Authorization':'Bearer sk_live_fixture'}):
                    with self.assertRaises(HTTPException) as blocked:
                        httpx.Client().send(httpx.Request('POST','https://api.stripe.com/v1/customers',headers=headers))
                    self.assertEqual(blocked.exception.status_code,503)
            finally:
                safety._installed=False
    def test_outbound_block(self):
        import httpx,smtplib,json as J
        env=ENV|{'BROQUER_STAGING_TEST_PHONES':'+52 443 111 2222','BROQUER_STAGING_TEST_EMAILS':'qa@example.test'}
        self.addCleanup(setattr,safety,'_installed',False)
        with patch.dict(safety.os.environ,env,clear=True),patch.object(httpx.Client,'send'),patch.object(httpx.AsyncClient,'send'),patch.object(smtplib.SMTP,'sendmail'):
            safety.install_staging_safety()
            post=lambda url,body=None:httpx.Client().send(httpx.Request('POST',url,json=body or {}))
            blocked=[('https://api.broquer.app/test',None),
                     ('https://graph.facebook.com/v21.0/123/messages',{'to':'5214430000000'}),
                     ('https://graph.facebook.com/v21.0/act_1/campaigns',{}),('https://graph.facebook.com/v21.0/1/feed',{}),
                     ('https://api.resend.com/emails',{'to':['cliente@real.mx']}),
                     ('https://api.resend.com/emails',{'to':['qa@example.test'],'bcc':['cliente@real.mx']}),
                     ('https://api.push.apple.com/3/device/x',{})]
            for url,body in blocked:
                with self.assertRaises(httpx.RequestError,msg=url):post(url,body)
            # Stripe without a test key: controlled 503 before any network call (#218).
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as stripe_blocked:post('https://api.stripe.com/v1/customers')
            self.assertEqual(stripe_blocked.exception.status_code,503)
            post('https://graph.facebook.com/v21.0/123/messages',{'to':'5214431112222'})
            post('https://api.resend.com/emails',{'to':'QA QA <qa@example.test>'})
            post('https://api.anthropic.com/v1/messages',{})
            post('https://qaexample.supabase.co/auth/v1/recover',{})
            s=smtplib.SMTP.__new__(smtplib.SMTP)
            with self.assertRaises(smtplib.SMTPException):smtplib.SMTP.sendmail(s,'a@b.c',['cliente@real.mx'],'x')
            safety._installed=False
if __name__=='__main__':unittest.main()
