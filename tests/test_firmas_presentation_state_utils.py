"""Behavior guards for pure Firmas presentation and state helpers."""
from __future__ import annotations

import unittest

from core.firmas_utils import _le_toca, _mail_layout, _resumen_estado


class FirmasPresentationStateUtilsTests(unittest.TestCase):
    def test_mail_layout_escapes_title_and_button_but_preserves_body_html(self):
        rendered = _mail_layout(
            "Firma <lista>",
            "<strong>Documento listo</strong>",
            "Abrir & firmar",
            "https://example.com/firma?a=1&b=2",
        )
        self.assertIn("Firma &lt;lista&gt;", rendered)
        self.assertIn("<strong>Documento listo</strong>", rendered)
        self.assertIn("Abrir &amp; firmar", rendered)
        self.assertIn("https://example.com/firma?a=1&amp;b=2", rendered)
        self.assertIn("background:#05203C", rendered)

    def test_mail_layout_omits_button_unless_text_and_url_are_both_present(self):
        self.assertNotIn("background:#05203C", _mail_layout("Título", "Cuerpo"))
        self.assertNotIn(
            "background:#05203C",
            _mail_layout("Título", "Cuerpo", boton_texto="Abrir"),
        )
        self.assertNotIn(
            "background:#05203C",
            _mail_layout("Título", "Cuerpo", boton_url="https://example.com"),
        )

    def test_turn_is_parallel_when_order_is_none(self):
        self.assertTrue(_le_toca({"orden": None}, [{"orden": 1, "estado": "pendiente"}]))

    def test_turn_blocks_on_earlier_required_unsigned_participant(self):
        firmante = {"orden": 3}
        todos = [
            {"orden": 1, "estado": "firmado", "obligatorio": True},
            {"orden": 2, "estado": "pendiente", "obligatorio": True},
            firmante,
        ]
        self.assertFalse(_le_toca(firmante, todos))

    def test_turn_ignores_optional_or_non_earlier_participants(self):
        firmante = {"orden": 2}
        todos = [
            {"orden": None, "estado": "pendiente", "obligatorio": True},
            {"orden": 1, "estado": "pendiente", "obligatorio": False},
            {"orden": 3, "estado": "pendiente", "obligatorio": True},
            firmante,
        ]
        self.assertTrue(_le_toca(firmante, todos))

    def test_summary_preserves_terminal_document_states(self):
        self.assertEqual(_resumen_estado({"estado": "cancelado"}, []), "cancelado")
        self.assertEqual(_resumen_estado({"estado": "borrador"}, []), "borrador")

    def test_summary_rejected_precedes_completion(self):
        firmantes = [
            {"estado": "firmado", "obligatorio": True},
            {"estado": "rechazado", "obligatorio": False},
        ]
        self.assertEqual(_resumen_estado({"estado": "enviado"}, firmantes), "rechazado")

    def test_summary_complete_partial_expired_and_sent_contract(self):
        self.assertEqual(
            _resumen_estado(
                {"estado": "enviado"},
                [{"estado": "firmado", "obligatorio": True}],
            ),
            "completo",
        )
        self.assertEqual(
            _resumen_estado(
                {"estado": "enviado"},
                [
                    {"estado": "firmado", "obligatorio": False},
                    {"estado": "pendiente", "obligatorio": True},
                ],
            ),
            "parcial",
        )
        self.assertEqual(
            _resumen_estado({"estado": "enviado", "vence_at": "2000-01-01T00:00:00Z"}, []),
            "vencido",
        )
        self.assertEqual(
            _resumen_estado({"estado": "enviado", "vence_at": "2999-01-01T00:00:00Z"}, []),
            "enviado",
        )
        self.assertEqual(
            _resumen_estado({"estado": "enviado", "vence_at": "fecha-invalida"}, []),
            "enviado",
        )


if __name__ == "__main__":
    unittest.main()
