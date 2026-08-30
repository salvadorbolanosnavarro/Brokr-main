"""Static domain vocabulary for electronic signatures.

These values are intentionally free of HTTP, persistence, storage, and runtime
configuration. The legal consent text intentionally remains explicit in the
router because it is part of the signature evidence contract.
"""
from __future__ import annotations


TIPOS = {
    "promesa": "Promesa de compraventa",
    "arrendamiento": "Contrato de arrendamiento",
    "exclusiva": "Contrato de exclusiva / mediación",
    "carta_intencion": "Carta de intención",
    "convenio": "Convenio de colaboración",
    "otro": "Documento",
}

ROLES = {
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
}

TIPOS_CON_AGENTE = {"exclusiva", "convenio"}
