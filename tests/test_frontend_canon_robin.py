import unittest
from pathlib import Path


class RobinCanonContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = Path('robin.html').read_text(encoding='utf-8')

    def test_robin_is_an_operational_surface_not_a_local_app_skin(self):
        self.assertIn('<body data-app="robin">', self.html)
        self.assertNotIn('class="rb-top"', self.html)
        self.assertNotIn('class="rb-hero"', self.html)
        self.assertIn('class="rb-pagehead"', self.html)
        self.assertIn('class="rb-summary"', self.html)

    def test_robin_keeps_existing_demo_interactions(self):
        for marker in (
            'id="lead-1"',
            'id="lead-2"',
            'id="lead-3"',
            'id="broq-resp"',
            'id="broq-input"',
            'id="trato-hoy"',
            'id="mes-monto"',
            'id="mes-n"',
            'window.rbHecho',
            'window.rbVendido',
            'window.rbBroq',
        ):
            self.assertIn(marker, self.html)

    def test_robin_uses_canon_tokens_for_visual_structure(self):
        for token in (
            'var(--paper)',
            'var(--ink)',
            'var(--line)',
            'var(--sky-blue)',
            'var(--page-max)',
            'var(--pad-x)',
        ):
            self.assertIn(token, self.html)


if __name__ == '__main__':
    unittest.main()
