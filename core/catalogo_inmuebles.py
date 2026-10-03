"""Catálogo único de inmuebles: tipos, operaciones y características.

Es la fuente de verdad. ``inmuebles-catalogo.js`` (frontend) se genera desde
aquí con ``python scripts/gen_catalogo_inmuebles.py`` y una prueba verifica
que ambos estén sincronizados.

Las claves (``key``) son las que se guardan en la base de datos. Las de tipo
conservan las seis claves que ya existían (casa, departamento, terreno, local,
oficina, bodega) para no romper datos ni búsquedas viejas.
"""
from __future__ import annotations

import re
import unicodedata

# ── Tipos de inmueble, agrupados ────────────────────────────────────────────
TIPOS = [
    {"grupo": "Residencial", "items": [
        {"key": "casa", "label": "Casa", "familia": "casa"},
        {"key": "casa_condominio", "label": "Casa en condominio", "familia": "casa"},
        {"key": "departamento", "label": "Departamento", "familia": "departamento"},
        {"key": "habitacion", "label": "Habitación", "familia": "departamento"},
        {"key": "quinta", "label": "Quinta", "familia": "casa"},
        {"key": "rancho", "label": "Rancho", "familia": "terreno"},
        {"key": "terreno", "label": "Terreno", "familia": "terreno"},
        {"key": "villa", "label": "Villa", "familia": "casa"},
    ]},
    {"grupo": "Comercial", "items": [
        {"key": "bodega", "label": "Bodega comercial", "familia": "bodega"},
        {"key": "casa_uso_suelo", "label": "Casa con uso de suelo", "familia": "casa"},
        {"key": "edificio", "label": "Edificio", "familia": "oficina"},
        {"key": "huerta", "label": "Huerta", "familia": "terreno"},
        {"key": "local", "label": "Local comercial", "familia": "local"},
        {"key": "local_centro_comercial", "label": "Local en centro comercial", "familia": "local"},
        {"key": "oficina", "label": "Oficina", "familia": "oficina"},
        {"key": "terreno_comercial", "label": "Terreno comercial", "familia": "terreno"},
    ]},
    {"grupo": "Industrial", "items": [
        {"key": "bodega_industrial", "label": "Bodega industrial", "familia": "bodega"},
        {"key": "nave_industrial", "label": "Nave industrial", "familia": "bodega"},
        {"key": "terreno_industrial", "label": "Terreno industrial", "familia": "terreno"},
    ]},
    {"grupo": "Otro", "items": [
        {"key": "otro", "label": "Otro", "familia": "otro"},
    ]},
]

# ``familia`` es el valor que se escribe en la columna vieja ``tipo`` (las seis
# claves de siempre + "otro"); el tipo detallado va en ``subtipo``. Así Bolsa,
# WhatsApp y las búsquedas viejas siguen funcionando sin cambios.

# Tipo de EasyBroker → clave Broquer (subtipo).
EB_TIPOS = {
    "Casa": "casa",
    "Casa en condominio": "casa_condominio",
    "Departamento": "departamento",
    "Departamento en condominio": "departamento",
    "Habitación": "habitacion",
    "Quinta": "quinta",
    "Rancho": "rancho",
    "Terreno": "terreno",
    "Villa": "villa",
    "Loft": "departamento",
    "Penthouse": "departamento",
    "Bodega comercial": "bodega",
    "Casa uso de suelo": "casa_uso_suelo",
    "Casa con uso de suelo": "casa_uso_suelo",
    "Edificio": "edificio",
    "Huerta": "huerta",
    "Local comercial": "local",
    "Local en centro comercial": "local_centro_comercial",
    "Oficina": "oficina",
    "Terreno comercial": "terreno_comercial",
    "Bodega industrial": "bodega_industrial",
    "Nave industrial": "nave_industrial",
    "Terreno industrial": "terreno_industrial",
    "Otro": "otro",
}

# ── Operaciones ─────────────────────────────────────────────────────────────
# ``legacy`` es el valor que se escribe en la columna vieja ``operacion``
# (venta/renta) para que Bolsa, WhatsApp y búsquedas sigan funcionando.
OPERACIONES = [
    {"key": "venta", "label": "Venta", "legacy": "venta"},
    {"key": "renta", "label": "Renta mensual", "legacy": "renta"},
    {"key": "preventa", "label": "Preventa", "legacy": "venta"},
    {"key": "renta_temporal", "label": "Renta temporal", "legacy": "renta"},
    {"key": "remate", "label": "Remate / adjudicada", "legacy": "venta"},
]
PERIODOS_TEMPORAL = [
    {"key": "noche", "label": "por noche"},
    {"key": "semana", "label": "por semana"},
    {"key": "mes", "label": "por mes"},
]
UNIDADES_PRECIO = [
    {"key": "total", "label": "Total"},
    {"key": "m2", "label": "por m²"},
    {"key": "ha", "label": "por hectárea"},
]

CONDICIONES = [
    {"key": "nuevo", "label": "Nuevo / a estrenar"},
    {"key": "excelente", "label": "Excelente"},
    {"key": "bueno", "label": "Bueno"},
    {"key": "regular", "label": "Regular"},
    {"key": "remodelar", "label": "Para remodelar"},
    {"key": "en_construccion", "label": "En construcción"},
]
DISPOSICIONES = [
    {"key": "frente", "label": "Frente"},
    {"key": "contrafrente", "label": "Contrafrente"},
    {"key": "interior", "label": "Interior"},
    {"key": "lateral", "label": "Lateral"},
]
ORIENTACIONES = [
    {"key": "norte", "label": "Norte"},
    {"key": "sur", "label": "Sur"},
    {"key": "oriente", "label": "Oriente"},
    {"key": "poniente", "label": "Poniente"},
    {"key": "noreste", "label": "Noreste"},
    {"key": "noroeste", "label": "Noroeste"},
    {"key": "sureste", "label": "Sureste"},
    {"key": "suroeste", "label": "Suroeste"},
]

# ── Características (casillas) ──────────────────────────────────────────────
# ``alias`` son otras formas de escribirlas (texto viejo de amenidades y
# nombres de features de EasyBroker). La comparación ignora mayúsculas,
# acentos y signos.
CARACTERISTICAS = [
    {"grupo": "Amenidades", "items": [
        {"key": "estacionamiento_visitas", "label": "Estacionamiento de visitas"},
        {"key": "area_comun", "label": "Áreas comunes", "alias": ["Área común", "Areas verdes", "Áreas verdes"]},
        {"key": "asador", "label": "Asador", "alias": ["Área de asador", "BBQ"]},
        {"key": "business_center", "label": "Business center", "alias": ["Centro de negocios"]},
        {"key": "casa_club", "label": "Casa club", "alias": ["Club house"]},
        {"key": "lavanderia", "label": "Lavandería", "alias": ["Cuarto de lavado", "Área de lavado"]},
        {"key": "acceso_controlado", "label": "Acceso controlado", "alias": ["Caseta de vigilancia", "Control de acceso"]},
        {"key": "pet_friendly_area", "label": "Área para mascotas", "alias": ["Pet park"]},
    ]},
    {"grupo": "Exterior", "items": [
        {"key": "acceso_playa", "label": "Acceso a la playa"},
        {"key": "anden", "label": "Andén"},
        {"key": "balcon", "label": "Balcón"},
        {"key": "cisterna", "label": "Cisterna"},
        {"key": "estacionamiento_techado", "label": "Estacionamiento techado", "alias": ["Cochera techada"]},
        {"key": "facil_estacionarse", "label": "Facilidad para estacionarse"},
        {"key": "frente_playa", "label": "Frente a la playa"},
        {"key": "frente_agua", "label": "Frente al agua"},
        {"key": "jardin", "label": "Jardín"},
        {"key": "patio", "label": "Patio"},
        {"key": "roof_garden", "label": "Roof garden", "alias": ["Roofgarden", "Azotea"]},
        {"key": "terraza", "label": "Terraza"},
        {"key": "vista_agua", "label": "Vista al agua"},
        {"key": "vista_mar", "label": "Vista al mar"},
        {"key": "vista_panoramica", "label": "Vista panorámica"},
    ]},
    {"grupo": "General", "items": [
        {"key": "aire_acondicionado", "label": "Aire acondicionado", "alias": ["A/C", "Clima", "Minisplit"]},
        {"key": "calefaccion", "label": "Calefacción"},
        {"key": "cocina_integral", "label": "Cocina integral", "alias": ["Cocina equipada"]},
        {"key": "cuarto_servicio", "label": "Cuarto de servicio"},
        {"key": "dos_plantas", "label": "Dos plantas"},
        {"key": "elevador", "label": "Elevador", "alias": ["Ascensor"]},
        {"key": "estudio", "label": "Estudio"},
        {"key": "fraccionamiento_privado", "label": "Fraccionamiento privado", "alias": ["Coto privado", "Privada"]},
        {"key": "hidroneumatico", "label": "Hidroneumático"},
        {"key": "oficina", "label": "Oficina"},
        {"key": "panel_solar", "label": "Panel solar", "alias": ["Paneles solares", "Calentador solar"]},
        {"key": "penthouse", "label": "Penthouse"},
        {"key": "planta_baja", "label": "Planta baja"},
        {"key": "planta_electrica", "label": "Planta eléctrica"},
        {"key": "portero", "label": "Portero", "alias": ["Conserje"]},
        {"key": "rampas", "label": "Rampas", "alias": ["Accesibilidad"]},
        {"key": "recamara_planta_baja", "label": "Recámara en planta baja"},
        {"key": "seguridad_12h", "label": "Seguridad 12 horas"},
        {"key": "seguridad_24h", "label": "Seguridad 24 horas", "alias": ["Seguridad 24h", "Vigilancia 24 horas", "Vigilancia 24h", "Seguridad"]},
        {"key": "una_planta", "label": "Una sola planta"},
        {"key": "vestidor", "label": "Vestidor"},
        {"key": "amueblado", "label": "Amueblado", "alias": ["Amueblada"]},
        {"key": "chimenea", "label": "Chimenea"},
        {"key": "closets", "label": "Closets", "alias": ["Clósets"]},
        {"key": "bodega_interna", "label": "Bodega / cuarto de guardado", "alias": ["Bodega"]},
        {"key": "internet", "label": "Internet / fibra óptica", "alias": ["Internet", "Fibra óptica", "Wifi"]},
        {"key": "gas_estacionario", "label": "Gas estacionario", "alias": ["Gas natural"]},
    ]},
    {"grupo": "Políticas", "items": [
        {"key": "mascotas_si", "label": "Mascotas permitidas", "alias": ["Se aceptan mascotas", "Pet friendly"]},
        {"key": "mascotas_no", "label": "No se aceptan mascotas"},
        {"key": "fumar_si", "label": "Permitido fumar"},
        {"key": "fumar_no", "label": "Prohibido fumar"},
    ]},
    {"grupo": "Recreación", "items": [
        {"key": "alberca", "label": "Alberca", "alias": ["Piscina"]},
        {"key": "juegos_infantiles", "label": "Área de juegos infantiles", "alias": ["Juegos infantiles", "Área infantil"]},
        {"key": "padel", "label": "Cancha de pádel", "alias": ["Pádel"]},
        {"key": "tenis", "label": "Cancha de tenis"},
        {"key": "cine", "label": "Cine", "alias": ["Sala de cine"]},
        {"key": "fogatero", "label": "Fogatero"},
        {"key": "gimnasio", "label": "Gimnasio", "alias": ["Gym"]},
        {"key": "jacuzzi", "label": "Jacuzzi"},
        {"key": "ludoteca", "label": "Ludoteca"},
        {"key": "salon_usos_multiples", "label": "Salón de usos múltiples", "alias": ["Salón de eventos", "SUM"]},
        {"key": "sauna", "label": "Sauna", "alias": ["Vapor"]},
        {"key": "cancha_futbol", "label": "Cancha de fútbol"},
        {"key": "cancha_basquetbol", "label": "Cancha de básquetbol"},
        {"key": "golf", "label": "Campo de golf", "alias": ["Golf"]},
    ]},
    {"grupo": "Financiamiento aceptado", "items": [
        {"key": "fin_bancario", "label": "Créditos bancarios", "alias": ["Crédito bancario", "Crédito hipotecario"]},
        {"key": "fin_infonavit", "label": "INFONAVIT / COFINAVIT", "alias": ["Infonavit", "Cofinavit"]},
        {"key": "fin_fovissste", "label": "FOVISSSTE", "alias": ["Fovisste"]},
        {"key": "fin_issfam", "label": "ISSFAM / Banjercito", "alias": ["Issfam", "Banjercito"]},
        {"key": "fin_pemex", "label": "PEMEX", "alias": ["Pemex"]},
    ]},
]


# Columnas que agregan las migraciones de paridad (migracion-fase*.sql). Si una
# base todavía no las tiene, los guardados reintentan sin ellas en vez de
# fallar (ver routers/propiedades_actualizar.py y el importador de EasyBroker).
COLUMNAS_PARIDAD = frozenset({
    "subtipo", "operaciones", "precio_unidad", "mantenimiento_incluido",
    "antiguedad", "condicion", "disposicion", "orientacion", "pisos_edificio",
    "caracteristicas", "otras_caracteristicas", "lat", "lng", "fecha_cierre",
})


def quitar_columnas_paridad(fila: dict) -> dict:
    return {k: v for k, v in fila.items() if k not in COLUMNAS_PARIDAD}


def es_error_columna_faltante(texto) -> bool:
    """¿PostgREST rechazó por una columna que no existe (migración pendiente)?"""
    t = str(texto or "")
    return "PGRST204" in t or ("Could not find the" in t and "column" in t)


def normaliza(texto) -> str:
    """minúsculas, sin acentos, sólo letras/números separados por un espacio."""
    if not texto:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _indice_caracteristicas() -> dict:
    idx = {}
    for grupo in CARACTERISTICAS:
        for it in grupo["items"]:
            for nombre in [it["label"], it["key"].replace("_", " "), *it.get("alias", [])]:
                idx.setdefault(normaliza(nombre), it["key"])
    return idx


_IDX_CARACT = _indice_caracteristicas()
TIPO_KEYS = {it["key"] for g in TIPOS for it in g["items"]}
_TIPO_FAMILIA = {it["key"]: it["familia"] for g in TIPOS for it in g["items"]}


_TIPO_LABEL = {it["key"]: it["label"] for g in TIPOS for it in g["items"]}


def tipo_label(key):
    """Nombre legible de un tipo del catálogo (o la clave tal cual)."""
    return _TIPO_LABEL.get(key, key or "")


def tipo_familia(subtipo):
    """Clave de la columna vieja ``tipo`` para un subtipo del catálogo."""
    return _TIPO_FAMILIA.get(subtipo)
OPERACION_KEYS = {o["key"] for o in OPERACIONES}
_OP_LEGACY = {o["key"]: o["legacy"] for o in OPERACIONES}


def caracteristica_de(texto):
    """Clave del catálogo para un texto libre, o None si no coincide."""
    return _IDX_CARACT.get(normaliza(texto))


def clasificar_amenidades(textos):
    """Separa textos libres en (claves del catálogo, textos sin coincidencia)."""
    claves, otras = [], []
    for t in textos or []:
        if not isinstance(t, str) or not t.strip():
            continue
        k = caracteristica_de(t)
        if k:
            if k not in claves:
                claves.append(k)
        elif t.strip() not in otras:
            otras.append(t.strip())
    return claves, otras


def operacion_legacy(key):
    """venta/renta para la columna vieja ``operacion``."""
    return _OP_LEGACY.get(key)


def catalogo_dict() -> dict:
    """Todo el catálogo como dict serializable (lo usa el generador de JS)."""
    return {
        "tipos": TIPOS,
        "operaciones": OPERACIONES,
        "periodos": PERIODOS_TEMPORAL,
        "unidades": UNIDADES_PRECIO,
        "condiciones": CONDICIONES,
        "disposiciones": DISPOSICIONES,
        "orientaciones": ORIENTACIONES,
        "caracteristicas": CARACTERISTICAS,
    }
