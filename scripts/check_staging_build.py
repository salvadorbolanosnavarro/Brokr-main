"""Meaningful isolation checks; no production network or keys involved."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
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
        for change in ({'STRIPE_SECRET_KEY':'sk_live_fixture'},{'RECORDATORIOS_ACTIVOS':'true'},{'BROQUER_STAGING_PROJECT_NAME':'broquer-beta'},{'SUPABASE_URL':build.PROD_DB}):
            with self.assertRaises(RuntimeError):safety.validate(ENV|change)
    def test_outbound_block(self):
        import httpx,smtplib,json as J
        env=ENV|{'BROQUER_STAGING_TEST_PHONES':'+52 443 111 2222','BROQUER_STAGING_TEST_EMAILS':'qa@example.test'}
        with patch.dict(safety.os.environ,env,clear=True),patch.object(httpx.Client,'send'),patch.object(httpx.AsyncClient,'send'),patch.object(smtplib.SMTP,'sendmail'):
            safety.install_staging_safety()
            post=lambda url,body=None:httpx.Client().send(httpx.Request('POST',url,json=body or {}))
            blocked=[('https://api.broquer.app/test',None),('https://api.stripe.com/v1/customers',None),
                     ('https://graph.facebook.com/v21.0/123/messages',{'to':'5214430000000'}),
                     ('https://graph.facebook.com/v21.0/act_1/campaigns',{}),('https://graph.facebook.com/v21.0/1/feed',{}),
                     ('https://api.resend.com/emails',{'to':['cliente@real.mx']}),
                     ('https://api.resend.com/emails',{'to':['qa@example.test'],'bcc':['cliente@real.mx']}),
                     ('https://api.push.apple.com/3/device/x',{})]
            for url,body in blocked:
                with self.assertRaises(httpx.RequestError,msg=url):post(url,body)
            post('https://graph.facebook.com/v21.0/123/messages',{'to':'5214431112222'})
            post('https://api.resend.com/emails',{'to':'QA QA <qa@example.test>'})
            post('https://api.anthropic.com/v1/messages',{})
            post('https://qaexample.supabase.co/auth/v1/recover',{})
            s=smtplib.SMTP.__new__(smtplib.SMTP)
            with self.assertRaises(smtplib.SMTPException):smtplib.SMTP.sendmail(s,'a@b.c',['cliente@real.mx'],'x')
            safety._installed=False
if __name__=='__main__':unittest.main()
