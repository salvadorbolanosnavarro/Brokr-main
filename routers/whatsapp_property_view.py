"""Pure property presentation helpers for WhatsApp conversations."""
from __future__ import annotations

from routers.whatsapp_utils import money as _money


def _texto_inmueble(p: dict) -> str:
    direccion = ", ".join(x for x in [p.get("calle"), p.get("colonia"), p.get("ciudad")] if x)
    det = []
    if p.get("recamaras"): det.append(f"{p['recamaras']} rec")
    if p.get("banos"): det.append(f"{p['banos']} baños")
    if p.get("m2_construccion"): det.append(f"{p['m2_construccion']} m2")
    precio = _money(p.get("precio"))
    return (f"*{p.get('titulo') or p.get('tipo') or 'Propiedad'}*\n"
            f"{direccion or 'Ubicación a consultar'}\n"
            f"{' · '.join(det)}\n"
            f"{precio} {p.get('moneda') or 'MXN'}" + (" / mes" if p.get("operacion") == "renta" else ""))


def _fotos_a_imagenes(fotos) -> list:
    out = []
    for f in (fotos or []):
        if isinstance(f, str) and f.strip():
            out.append({"url": f.strip()})
        elif isinstance(f, dict):
            u = f.get("url") or f.get("original")
            if u:
                out.append({"url": u})
    return out


def _propiedad_para_ficha(p: dict) -> dict:
    """Map a property row to the existing technical-sheet payload contract."""
    op_raw = (p.get("operacion") or "").strip().lower()
    op_type = "rental" if op_raw == "renta" else "sale"
    operations = []
    if p.get("precio"):
        operations.append({"type": op_type, "amount": p.get("precio"), "currency": p.get("moneda") or "MXN"})
    calle = " ".join(filter(None, [str(p.get("calle") or "").strip(), str(p.get("num_exterior") or "").strip()])).strip()
    return {
        "public_id": p.get("id") or "", "id": p.get("id") or "",
        "title": p.get("titulo") or p.get("tipo") or "Propiedad",
        "property_type": p.get("tipo") or "Propiedad",
        "operations": operations,
        "location": {"name": p.get("colonia") or "", "city": p.get("ciudad") or ""},
        "address": calle,
        "bedrooms": p.get("recamaras"), "bathrooms": p.get("banos"),
        "parking_spaces": p.get("estacionamientos"),
        "construction_size": p.get("m2_construccion"), "lot_size": p.get("m2_terreno"),
        "description": p.get("descripcion") or "",
        "property_images": _fotos_a_imagenes(p.get("fotos")),
    }
