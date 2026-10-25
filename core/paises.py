"""Países donde opera Broquer: la única fuente de verdad del lado del servidor.

Cada cuenta pertenece a UN país (columna ``usuarios.pais``). Se elige en el
landing antes de crear la cuenta y ya no se vuelve a preguntar; los miembros
de un equipo heredan el país del dueño de la empresa.

El espejo para el navegador es ``paises.js``; si agregas un país o cambias
un dato aquí, cámbialo también allá (``tests/test_paises.py`` lo verifica).
"""
from __future__ import annotations

import logging
import re
from typing import Dict, Optional

import httpx

from core.database import get_rows, patch_rows

log = logging.getLogger(__name__)

PAIS_DEFAULT = "MX"

PAISES: Dict[str, dict] = {
    "MX": {
        "nombre": "México",
        "moneda": "MXN",
        "monedas": ("MXN", "USD"),
        "lada": "52",
        "digitos_tel": 10,
        "zona_horaria": "America/Mexico_City",
        "dominio_google": "google.com.mx",
        "gl": "mx",
        "id_fiscal": "RFC",
        "autoridad_fiscal": "SAT",
        "impuesto_venta": "ISR por enajenación",
        "portales": {
            "inmuebles24.com": "Inmuebles24",
            "lamudi.com.mx": "Lamudi",
            "propiedades.com": "Propiedades.com",
            "vivanuncios.com.mx": "Vivanuncios",
            "mercadolibre.com.mx": "Mercado Libre Inmuebles",
        },
        "cobro_moneda": "mxn",
        # Moneda en la que el mercado publica y en la que el AVM da el valor.
        "moneda_avm": "MXN",
        # Ley que respalda la firma electrónica (consentimiento y constancia).
        "ley_firma": "los artículos 89 a 114 del Código de Comercio",
    },
    "CO": {
        "nombre": "Colombia",
        "moneda": "COP",
        "monedas": ("COP", "USD"),
        "lada": "57",
        "digitos_tel": 10,
        "zona_horaria": "America/Bogota",
        "dominio_google": "google.com.co",
        "gl": "co",
        "id_fiscal": "NIT",
        "autoridad_fiscal": "DIAN",
        "impuesto_venta": "ganancia ocasional",
        "portales": {
            "fincaraiz.com.co": "Finca Raíz",
            "metrocuadrado.com": "Metrocuadrado",
            "ciencuadras.com": "Ciencuadras",
            "properati.com.co": "Properati",
            "mercadolibre.com.co": "Mercado Libre Inmuebles",
        },
        "cobro_moneda": "usd",
        # Moneda en la que el mercado publica y en la que el AVM da el valor.
        "moneda_avm": "COP",
        # Ley que respalda la firma electrónica (consentimiento y constancia).
        "ley_firma": "la Ley 527 de 1999 y el Decreto 2364 de 2012",
    },
    "PE": {
        "nombre": "Perú",
        "moneda": "PEN",
        "monedas": ("PEN", "USD"),
        "lada": "51",
        "digitos_tel": 9,
        "zona_horaria": "America/Lima",
        "dominio_google": "google.com.pe",
        "gl": "pe",
        "id_fiscal": "RUC",
        "autoridad_fiscal": "SUNAT",
        "impuesto_venta": "impuesto a la renta de segunda categoría",
        "portales": {
            "urbania.pe": "Urbania",
            "adondevivir.com": "Adondevivir",
            "properati.com.pe": "Properati",
            "nexoinmobiliario.pe": "Nexo Inmobiliario",
            "mercadolibre.com.pe": "Mercado Libre Inmuebles",
        },
        "cobro_moneda": "usd",
        # Moneda en la que el mercado publica y en la que el AVM da el valor.
        "moneda_avm": "USD",
        # Ley que respalda la firma electrónica (consentimiento y constancia).
        "ley_firma": "la Ley N.º 27269, Ley de Firmas y Certificados Digitales, y su Reglamento",
    },
    "AR": {
        "nombre": "Argentina",
        "moneda": "ARS",
        "monedas": ("USD", "ARS"),
        "lada": "54",
        "digitos_tel": 10,
        "zona_horaria": "America/Argentina/Buenos_Aires",
        "dominio_google": "google.com.ar",
        "gl": "ar",
        "id_fiscal": "CUIT",
        "autoridad_fiscal": "ARCA",
        "impuesto_venta": "impuesto cedular",
        "portales": {
            "zonaprop.com.ar": "Zonaprop",
            "argenprop.com": "Argenprop",
            "properati.com.ar": "Properati",
            "inmuebles.mercadolibre.com.ar": "Mercado Libre Inmuebles",
            "mercadolibre.com.ar": "Mercado Libre Inmuebles",
        },
        "cobro_moneda": "usd",
        # Moneda en la que el mercado publica y en la que el AVM da el valor.
        "moneda_avm": "USD",
        # Ley que respalda la firma electrónica (consentimiento y constancia).
        "ley_firma": "la Ley 25.506 de Firma Digital y los artículos 286 a 288 del Código Civil y Comercial de la Nación",
    },
    "CL": {
        "nombre": "Chile",
        "moneda": "CLP",
        "monedas": ("CLP", "UF", "USD"),
        "lada": "56",
        "digitos_tel": 9,
        "zona_horaria": "America/Santiago",
        "dominio_google": "google.cl",
        "gl": "cl",
        "id_fiscal": "RUT",
        "autoridad_fiscal": "SII",
        "impuesto_venta": "impuesto al mayor valor en bienes raíces",
        "portales": {
            "portalinmobiliario.com": "Portal Inmobiliario",
            "toctoc.com": "TocToc",
            "yapo.cl": "Yapo",
            "propiedades.emol.com": "Propiedades Emol",
            "mercadolibre.cl": "Mercado Libre Inmuebles",
        },
        "cobro_moneda": "usd",
        # Moneda en la que el mercado publica y en la que el AVM da el valor.
        "moneda_avm": "UF",
        # Ley que respalda la firma electrónica (consentimiento y constancia).
        "ley_firma": "la Ley N.º 19.799 sobre Documentos Electrónicos, Firma Electrónica y Servicios de Certificación",
    },
}


def normalizar_pais(codigo: Optional[str]) -> str:
    """Código de país válido; cualquier cosa desconocida es México."""
    c = (codigo or "").strip().upper()
    return c if c in PAISES else PAIS_DEFAULT


def datos_pais(codigo: Optional[str]) -> dict:
    return PAISES[normalizar_pais(codigo)]


def nombre_pais(codigo: Optional[str]) -> str:
    return datos_pais(codigo)["nombre"]


async def pais_de_usuario(user_id: Optional[str]) -> str:
    """País de la cuenta. Las cuentas anteriores a la expansión son de México."""
    if not user_id:
        return PAIS_DEFAULT
    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "pais", "limit": "1"},
            timeout=8,
        )
    except (httpx.HTTPError, RuntimeError):
        return PAIS_DEFAULT
    return normalizar_pais((rows[0] if rows else {}).get("pais"))


async def heredar_pais(user_id: str, de_user_id: str) -> None:
    """Un miembro nuevo de un equipo trabaja en el país del dueño."""
    pais = await pais_de_usuario(de_user_id)
    try:
        await patch_rows(
            "usuarios",
            {"id": f"eq.{user_id}"},
            {"pais": pais},
            prefer="return=minimal",
            timeout=8,
        )
    except httpx.HTTPError as e:
        # Unirse al equipo no se cae por esto; el país se corrige a mano.
        log.warning("No se pudo heredar el país %s a %s: %s", pais, user_id, e)


def telefono_e164(numero: str, pais: Optional[str] = None) -> str:
    """Normaliza un teléfono a E.164 usando la lada del país de la cuenta.

    Acepta números locales (solo los dígitos nacionales) o ya con lada.
    """
    d = re.sub(r"\D", "", numero or "")
    if not d:
        return ""
    cfg = datos_pais(pais)
    if len(d) == cfg["digitos_tel"]:
        return "+" + cfg["lada"] + d
    return "+" + d


def contexto_ia(pais: Optional[str]) -> str:
    """Bloque que se agrega al prompt de Broq y de la IA de WhatsApp cuando
    la cuenta no es de México (los prompts base están escritos para México)."""
    c = normalizar_pais(pais)
    if c == PAIS_DEFAULT:
        return ""
    cfg = PAISES[c]
    return (
        f"\n\nPAÍS DEL USUARIO: trabaja en {cfg['nombre']}. Esto manda sobre todo lo anterior que hable "
        f"de México: usa {cfg['moneda']} como moneda por defecto, el español de {cfg['nombre']} y la ley, los "
        f"impuestos y las autoridades de {cfg['nombre']} ({cfg['autoridad_fiscal']}, {cfg['id_fiscal']}). No "
        "apliques ISR mexicano, SAT, LFPIORPI, UMA, UDIS, INPC, Código de Comercio ni LFPDPPP. Los contratos "
        "de Broquer y el módulo de Cumplimiento ya están adaptados a su país; el de ISR no existe para él. "
        "Para impuestos por la venta de un "
        f"inmueble usa calcular_isr: abre la calculadora de {cfg['impuesto_venta']} de {cfg['nombre']}. "
        "Si no estás seguro de una norma local, dilo y verifícala con web_search."
    )


def contexto_whatsapp(pais: Optional[str]) -> str:
    """Lo mismo para la IA que atiende prospectos por WhatsApp."""
    c = normalizar_pais(pais)
    if c == PAIS_DEFAULT:
        return ""
    cfg = PAISES[c]
    return (
        f"\n\nPAÍS: el asesor trabaja en {cfg['nombre']}. Habla con el español de {cfg['nombre']}, no con "
        f"el mexicano. Los precios y presupuestos son en {cfg['moneda']} salvo que el prospecto diga otra "
        f"moneda; en registrar_inmueble usa \"moneda\":\"{cfg['moneda']}\" o la que te digan, y convierte "
        "el presupuesto a un número entero en esa moneda."
    )
