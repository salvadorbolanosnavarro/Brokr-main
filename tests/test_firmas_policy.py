"""Literal guards for the static electronic-signature domain vocabulary."""
from __future__ import annotations

import unittest

from core.firmas_policy import ROLES, TIPOS, TIPOS_CON_AGENTE


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


if __name__ == "__main__":
    unittest.main()
