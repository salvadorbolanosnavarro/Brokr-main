"""The commercial rebrand must not alter the application's contracts."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from staging_brand import brand_asset


class StagingBrandTests(unittest.TestCase):
    def test_assistant_name_and_voice_aliases_preserve_internal_keys(self):
        result = brand_asset('app-shell.js', "const WAKE = ['broq'];const label='Abrir Broq';const key='broq-history';window.openBroq();")
        self.assertIn("label='Abrir Cecil IA'", result)
        self.assertIn("'cecil ia'", result)
        self.assertIn("'broq'", result)
        self.assertIn("key='broq-history'", result)
        self.assertIn('window.openBroq()', result)

    def test_stylesheet_is_only_injected_into_document_head(self):
        source = '<head></head><script>const html="</head>";</script>'
        result = brand_asset('estadisticas.html', source)
        self.assertEqual(result.count('staging-brand.css'), 1)
        self.assertIn('const html="</head>";', result)

    def test_display_copy_changes_but_contracts_and_urls_do_not(self):
        source = '''<title>Broquer · Inicio</title>
        <button id="broquer-login" onclick="showBroquerMaxModal()">Entrar a Broquer</button>
        <a href="mailto:hola@broquer.app?subject=Broquer%20Max">Broquer Max</a>
        <script>window.BroquerEditorImages=[];
        postMessage({type:'Broquer-use-in-ficha'});
        const API='https://api.broquer.app';localStorage.getItem('broquer-session');</script>'''
        result = brand_asset('index.html', source)
        self.assertIn('<title>Comisión Fácil · Inicio</title>', result)
        for token in ['id="broquer-login"', 'onclick="showBroquerMaxModal()"',
                      'mailto:hola@broquer.app?subject=Broquer%20Max',
                      "'Broquer-use-in-ficha'", 'window.BroquerEditorImages',
                      "'https://api.broquer.app'", "localStorage.getItem('broquer-session')"]:
            self.assertIn(token, result)

    def test_logo_sources_and_accessible_name(self):
        source = '<a class="bk-design-brand" href="index.html" aria-label="Broquer, inicio">broquer<span>.</span></a>'
        result = brand_asset('index.html', source)
        self.assertIn('alt="Comisión Fácil"', result)
        self.assertIn('href="index.html"', result)
        self.assertIn('media="(max-width:720px)"', result)
        self.assertNotIn('broquer<span>', result)

    def test_supplied_logos_do_not_replace_agent_or_provider_artwork(self):
        source = '<img src="../logotipo-black.png"><img src="logo-inmobiliaria-navarro.png"><img src="meta-tech-provider.png">'
        result = brand_asset('preview-modo/index.html', source)
        self.assertIn('src="/brand/comision-facil-wordmark.svg"', result)
        self.assertIn('src="logo-inmobiliaria-navarro.png"', result)
        self.assertIn('src="meta-tech-provider.png"', result)
