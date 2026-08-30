"""Literal guards for the static electronic-signature domain policy."""
from __future__ import annotations

import unittest

from core.firmas_policy import CONSENTIMIENTO, ROLES, TIPOS, TIPOS_CON_AGENTE


class FirmasPolicyTests(unittest.TestCase):
    def test_document_type_vocabulary_is_exact(self):
        self.assertEqual(
            TIPOS,
            {
                "promesa": "Promesa de compraventa",
                "arrendamiento": "Contrato de arrendamiento",
                "exclusiva": "Contrato de exclusiva / mediación",
                "carta_intencion": "Carta de intención",
                "convenio": "Convenio de colaboración",
                "otro": "Documento",
            },
        )

    def test_signer_role_vocabulary_is_exact(self):
        self.assertEqual(
            ROLES,
            {
                "promitente_vendedor": "Promitente vendedor",
                "promitente_comprador": "Promitente comprador",
                "arrendador": "Arrendador",
                "arrendatario": "Arrendatario",
                "fiador": "Fiador",
                "obligado_solidario": "Obligado solidario",
                "copropietario": "Copropietario",
                "conyuge": "Cónyuge",
                "propietario": "Propietario",
                "agente_mediador": "Asesor inmobiliario",
                "testigo": "Testigo",
                "otro": "Firmante",
            },
        )

    def test_agent_allowed_types_are_exact(self):
        self.assertEqual(TIPOS_CON_AGENTE, {"exclusiva", "convenio"})

    def test_consent_literal_preserves_legal_invariants(self):
        self.assertIn("artículos 89 a 114 del Código de Comercio", CONSENTIMIENTO)
        self.assertIn("mismo valor y efectos que mi firma autógrafa", CONSENTIMIENTO)
        self.assertIn("bajo mi control exclusivo", CONSENTIMIENTO)
        self.assertEqual(
            CONSENTIMIENTO,
            "Manifiesto que leí íntegramente el documento que se me presentó, que "
            "entiendo su contenido y alcance, y que es mi voluntad obligarme en sus "
            "términos. Acepto expresamente manifestar mi consentimiento por medios "
            "electrónicos y reconozco que la firma electrónica que produzco en este "
            "acto tiene, respecto de mi persona, el mismo valor y efectos que mi firma "
            "autógrafa, en términos de los artículos 89 a 114 del Código de Comercio. "
            "Reconozco que quedará registrada la fecha y hora de mi firma, la dirección "
            "IP desde la que firmo, el dispositivo que utilizo, la ubicación aproximada "
            "que autorice compartir y el código de verificación que recibí, y consiento "
            "que esa información se conserve como evidencia del acto. Confirmo que el "
            "número de teléfono o correo donde recibí el código de verificación es mío "
            "y está bajo mi control exclusivo.",
        )


if __name__ == "__main__":
    unittest.main()
