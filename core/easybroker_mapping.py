"""Pure EasyBroker-to-Broquer property normalization helpers."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Optional

from core.catalogo_inmuebles import (
    EB_TIPOS,
    clasificar_amenidades,
    operacion_legacy,
    quitar_columnas_paridad,
    tipo_familia,
)


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


_EB_OP_TIPO = {"sale": "venta", "rental": "renta", "temporary_rental": "renta_temporal"}
_EB_UNIDAD = {"total": "total", "square_meter": "m2", "m2": "m2", "hectare": "ha", "ha": "ha"}
_EB_PERIODO = {"daily": "noche", "nightly": "noche", "weekly": "semana", "monthly": "mes"}

# Si la base aún no tiene las columnas de paridad, el importador reintenta sin
# ellas (ver routers/easybroker_migration.py).
quitar_columnas_extendidas = quitar_columnas_paridad


def _to_coord(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f != 0 and -180 <= f <= 180 else None


_YT_RE = re.compile(r"(?:youtu\.be/|youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/|v/))([A-Za-z0-9_-]{11})")


def _eb_ligas(valores, solo_youtube: bool = False) -> list:
    """Ligas https únicas de una lista de textos u objetos {"url": …}."""
    out = []
    for v in valores or []:
        url = (v.get("url") or v.get("link") or "") if isinstance(v, dict) else (v or "")
        url = str(url).strip()
        if not url:
            continue
        if solo_youtube:
            m = _YT_RE.search(url)
            if not m:
                continue
            url = f"https://www.youtube.com/watch?v={m.group(1)}"
        elif not url.startswith("https://"):
            continue
        if url not in out:
            out.append(url)
    return out


def _eb_operaciones(ops) -> list:
    """Operaciones de EasyBroker → lista de operaciones Broquer."""
    out = []
    for op in ops or []:
        if not isinstance(op, dict):
            continue
        tipo = _EB_OP_TIPO.get(op.get("type"))
        if not tipo:
            continue
        try:
            precio = float(op.get("amount")) if op.get("amount") else None
        except (TypeError, ValueError):
            precio = None
        item = {
            "tipo": tipo,
            "precio": precio,
            "moneda": (op.get("currency") or "MXN").upper(),
            "unidad": _EB_UNIDAD.get(op.get("unit") or "total", "total"),
        }
        periodo = _EB_PERIODO.get(op.get("period") or "")
        if tipo == "renta_temporal":
            item["periodo"] = periodo or "noche"
        out.append(item)
    return out


def _split_location_name(name):
    """Parte "Colonia, Municipio, Estado" de EasyBroker en sus tres piezas.

    Con más de tres partes, las dos últimas son municipio y estado y el resto
    es la colonia. Las piezas que no vengan se regresan como None.
    """
    if not name or not isinstance(name, str):
        return (None, None, None)
    parts = [p.strip() for p in name.split(",") if p.strip()]
    if not parts:
        return (None, None, None)
    if len(parts) == 1:
        return (parts[0], None, None)
    if len(parts) == 2:
        return (parts[0], parts[1], None)
    return (", ".join(parts[:-2]), parts[-2], parts[-1])


def _texto(v, largo: int) -> Optional[str]:
    v = str(v).strip() if v not in (None, "") else ""
    return v[:largo] or None


def eb_extras(prop_full: dict) -> dict:
    """Datos de EasyBroker que no van directo a una columna del inmueble:
    descripción privada (→ notas internas), agente asignado y propietario.
    La API los ha mandado con varios nombres; se aceptan todos."""
    nota = next((prop_full.get(k) for k in ("private_description", "internal_notes", "private_notes", "notes")
                 if isinstance(prop_full.get(k), str) and prop_full.get(k).strip()), None)
    agente = prop_full.get("agent") if isinstance(prop_full.get("agent"), dict) else None
    dueno = next((prop_full.get(k) for k in ("owner", "property_owner", "owner_contact")
                  if isinstance(prop_full.get(k), dict)), None)
    propietario = None
    if dueno:
        tel = dueno.get("phone") or dueno.get("mobile_phone") or dueno.get("cell_phone") or ""
        if not tel and isinstance(dueno.get("phones"), list) and dueno["phones"]:
            p0 = dueno["phones"][0]
            tel = p0.get("phone") if isinstance(p0, dict) else p0
        email = dueno.get("email") or ""
        if not email and isinstance(dueno.get("emails"), list) and dueno["emails"]:
            e0 = dueno["emails"][0]
            email = e0.get("email") if isinstance(e0, dict) else e0
        nombre = (dueno.get("full_name") or dueno.get("name")
                  or " ".join(x for x in (dueno.get("first_name"), dueno.get("last_name")) if x) or "").strip()
        tel = re.sub(r"[^+\d]", "", str(tel or ""))[:20]
        email = str(email or "").strip().lower()[:120]
        if nombre or tel or email:
            propietario = {"nombre": nombre[:120] or "Propietario", "telefono": tel, "email": email}
    return {"nota_privada": nota.strip()[:4000] if nota else None, "agente": agente, "propietario": propietario}


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

    tipo_eb = prop_full.get("property_type", "") or ""
    subtipo = EB_TIPOS.get(tipo_eb)
    if subtipo:
        tipo = tipo_familia(subtipo)
    else:
        tipo = _EB_TIPO_MAP.get(tipo_eb, tipo_eb.lower() if tipo_eb else None)

    operaciones_eb = prop_full.get("operations", []) or []
    operaciones = _eb_operaciones(operaciones_eb)
    operacion = None
    precio = None
    moneda = "MXN"
    if operaciones:
        # La operación principal (columnas viejas): venta primero, luego renta.
        principal = (next((o for o in operaciones if o["tipo"] == "venta"), None)
                     or next((o for o in operaciones if o["tipo"] == "renta"), None)
                     or operaciones[0])
        operacion = operacion_legacy(principal["tipo"])
        precio = principal.get("precio")
        moneda = principal.get("moneda") or "MXN"
        # La principal va primero en la lista.
        operaciones = [principal] + [o for o in operaciones if o is not principal]

    location_raw = prop_full.get("location") or ""
    colonia = None
    # Sin default geográfico: un "Morelia" inventado se pegaba a inmuebles de
    # otras ciudades. Si EasyBroker no trae el dato, se queda vacío.
    ciudad = None
    estado = None
    cp_from_loc = None
    if isinstance(location_raw, dict):
        # La API v1 de EasyBroker manda la ubicación como un solo texto en
        # "name" ("Ciudad Granja, Zapopan, Jalisco"), sin "city" ni "region".
        # Antes ese texto completo se guardaba como colonia y la ciudad caía
        # a un default Morelia → "Ciudad Granja, Zapopan, Jalisco, Morelia".
        col_n, ciu_n, est_n = _split_location_name(location_raw.get("name"))
        colonia = location_raw.get("city_area") or location_raw.get("neighborhood") or col_n or None
        ciudad = location_raw.get("city") or location_raw.get("municipality") or ciu_n or None
        estado = location_raw.get("region") or location_raw.get("state") or est_n or None
        cp_from_loc = location_raw.get("postal_code") or None
    elif isinstance(location_raw, str) and location_raw:
        col_n, ciu_n, est_n = _split_location_name(location_raw)
        colonia = col_n
        ciudad = ciu_n
        estado = est_n

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

    # features llega como lista de textos o de objetos {"name", "category"}.
    features = prop_full.get("features") or []
    nombres_features = []
    for f in features:
        nombre = f.get("name") if isinstance(f, dict) else f
        if isinstance(nombre, str) and nombre.strip():
            nombres_features.append(nombre.strip())
    amenidades = nombres_features or None
    caracteristicas, otras = clasificar_amenidades(nombres_features)

    lat = lng = None
    if isinstance(location_raw, dict):
        lat = _to_coord(location_raw.get("latitude") or location_raw.get("lat"))
        lng = _to_coord(location_raw.get("longitude") or location_raw.get("lng"))

    # "age" en EasyBroker puede venir como año de construcción o como años de
    # antigüedad; un número de año (>= 1800) se toma como año.
    edad = _to_int(prop_full.get("age"))
    anio_construccion = edad if edad and edad >= 1800 else None
    antiguedad = edad if edad and edad < 1800 else None

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
        "anio_construccion": anio_construccion,
        "descripcion": prop_full.get("description") or None,
        "amenidades": amenidades,
        "fotos": fotos,
        # ── Columnas de paridad (migracion-fase1-inventario.sql) ──
        "subtipo": subtipo,
        "operaciones": operaciones,
        "precio_unidad": (operaciones[0].get("unidad") if operaciones else None) or "total",
        "antiguedad": antiguedad,
        "caracteristicas": caracteristicas,
        "otras_caracteristicas": ", ".join(otras) or None,
        "lat": lat,
        "lng": lng,
        # Fase 2 (migracion-fase2-multimedia.sql)
        "videos": _eb_ligas(prop_full.get("videos"), solo_youtube=True),
        "tours": _eb_ligas([prop_full.get("virtual_tour"), *(prop_full.get("virtual_tours") or [])]),
        # Fase 9: clave interna, código de llave y etiquetas de EasyBroker.
        "clave_interna": _texto(prop_full.get("internal_id"), 60),
        "codigo_llave": _texto(prop_full.get("key_code") or prop_full.get("keys_location") or prop_full.get("key_location"), 120),
        "etiquetas": [str(t).strip()[:40] for t in (prop_full.get("tags") or []) if isinstance(t, str) and t.strip()][:40],
        "updated_at": datetime.utcnow().isoformat(),
    }
