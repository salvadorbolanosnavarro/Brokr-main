"""Pure EasyBroker-to-Broquer property normalization helpers."""
from __future__ import annotations

from datetime import datetime
import re


_EB_TIPO_MAP = {
    "Casa": "casa",
    "Casa en condominio": "casa",
    "Departamento": "departamento",
    "Departamento en condominio": "departamento",
    "Terreno": "terreno",
    "Terreno comercial": "terreno",
    "Local comercial": "local",
    "Local en centro comercial": "local",
    "Oficina": "oficina",
    "Edificio": "oficina",
    "Bodega comercial": "bodega",
    "Bodega industrial": "bodega",
    "Nave industrial": "bodega",
    "Rancho": "terreno",
    "Quinta": "casa",
    "Villa": "casa",
    "Loft": "departamento",
    "Penthouse": "departamento",
    "Casa uso de suelo": "casa",
}

_EB_STATUS_MAP = {
    "published": "activa",
    "not_published": "suspendida",
    "reserved": "reservada",
    "sold": "vendida",
    "rented": "rentada",
}

_EB_STATUS_DEFAULT = ["published", "reserved", "sold", "rented"]
_EB_LIMITE_PROPIEDADES = 1000


def _split_street(s: str):
    """Separa calle, número exterior e interior conservando el parser legacy."""
    if not s or not isinstance(s, str):
        return (None, None, None)
    s = s.strip()
    int_match = re.search(
        r'[\s,]+(?:int\.?|interior|depto\.?|departamento)\s*([0-9A-Za-z\-]+)\s*$',
        s,
        re.IGNORECASE,
    )
    num_int = None
    if int_match:
        num_int = int_match.group(1)
        s = s[:int_match.start()].strip()
    ext_match = re.search(r'^(.+?)[\s,#]+([0-9]+[A-Za-z\-]?)\s*$', s)
    if ext_match:
        return (ext_match.group(1).strip(), ext_match.group(2).strip(), num_int)
    return (s, None, num_int)


def _eb_to_brokr(prop_full: dict, user_id: str) -> dict:
    """Mapea una propiedad de EasyBroker al esquema de propiedades de Broquer."""
    def _to_int(v):
        try:
            return int(float(v)) if v not in (None, "", 0) else None
        except Exception:
            return None

    def _to_float(v):
        try:
            return float(v) if v not in (None, "", 0) else None
        except Exception:
            return None

    tipo_eb = prop_full.get("property_type", "")
    tipo = _EB_TIPO_MAP.get(tipo_eb, tipo_eb.lower() if tipo_eb else None)

    operaciones = prop_full.get("operations", []) or []
    operacion = None
    precio = None
    moneda = "MXN"
    if operaciones:
        op_venta = next((o for o in operaciones if o.get("type") == "sale"), None)
        op_renta = next((o for o in operaciones if o.get("type") == "rental"), None)
        op = op_venta or op_renta or operaciones[0]
        if op.get("type") == "sale":
            operacion = "venta"
        elif op.get("type") == "rental":
            operacion = "renta"
        amount = op.get("amount") or 0
        precio = float(amount) if amount else None
        moneda = (op.get("currency") or "MXN").upper()

    location_raw = prop_full.get("location") or ""
    colonia = None
    ciudad = "Morelia"
    estado = "Michoacán"
    cp_from_loc = None
    if isinstance(location_raw, dict):
        colonia = location_raw.get("city_area") or location_raw.get("name") or location_raw.get("neighborhood") or None
        ciudad = location_raw.get("city") or location_raw.get("municipality") or "Morelia"
        estado = location_raw.get("region") or location_raw.get("state") or "Michoacán"
        cp_from_loc = location_raw.get("postal_code") or None
    elif isinstance(location_raw, str) and location_raw:
        parts = [p.strip() for p in location_raw.split(",")]
        colonia = parts[0] if parts else None
        ciudad = parts[1] if len(parts) > 1 else "Morelia"
        estado = parts[2] if len(parts) > 2 else "Michoacán"

    street_raw = prop_full.get("street") or ""
    if not street_raw and isinstance(location_raw, dict):
        street_raw = location_raw.get("street") or ""
    calle, num_ext, num_int = _split_street(street_raw)

    cp = prop_full.get("postal_code") or cp_from_loc or None

    property_images = prop_full.get("property_images", []) or []
    fotos = []
    title_img = prop_full.get("title_image_full") or prop_full.get("title_image_thumb")
    if title_img:
        fotos.append(title_img)
    for img in property_images:
        url = img.get("url") or img.get("title_image_full") or img.get("image_url")
        if url and url not in fotos:
            fotos.append(url)

    features = prop_full.get("features") or []
    amenidades = [f for f in features if isinstance(f, str) and f.strip()] or None

    return {
        "user_id": user_id,
        "eb_public_id": prop_full.get("public_id"),
        "titulo": prop_full.get("title") or "Propiedad",
        "tipo": tipo,
        "operacion": operacion,
        "estatus": "activa",
        "precio": precio,
        "moneda": moneda,
        "calle": calle or street_raw or None,
        "num_exterior": num_ext,
        "num_interior": num_int,
        "colonia": colonia,
        "ciudad": ciudad,
        "estado": estado,
        "cp": cp,
        "m2_construccion": _to_float(prop_full.get("construction_size")),
        "m2_terreno": _to_float(prop_full.get("lot_size")),
        "recamaras": _to_int(prop_full.get("bedrooms")),
        "banos": _to_float(prop_full.get("bathrooms")),
        "medio_bano": _to_int(prop_full.get("half_bathrooms")),
        "estacionamientos": _to_int(prop_full.get("parking_spaces")),
        "nivel": str(prop_full.get("floor")) if prop_full.get("floor") not in (None, "") else None,
        "mantenimiento": _to_float(prop_full.get("expenses")),
        "anio_construccion": _to_int(prop_full.get("age")),
        "descripcion": prop_full.get("description") or None,
        "amenidades": amenidades,
        "fotos": fotos,
        "updated_at": datetime.utcnow().isoformat(),
    }
