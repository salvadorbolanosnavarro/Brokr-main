"""Coincidencias entre requerimientos de clientes e inmuebles.

``coincide(req, prop)`` es pura (sin red) y la usan: la pestaña Requerimiento
(inventario propio/equipo/Bolsa), "Buscar clientes potenciales" desde la ficha
del inmueble y el ciclo diario de alertas.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.catalogo_inmuebles import clasificar_amenidades, normaliza, tipo_familia


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def operaciones_de(prop: dict) -> List[dict]:
    ops = [o for o in (prop.get("operaciones") or []) if isinstance(o, dict) and o.get("tipo")]
    if ops:
        return ops
    if prop.get("operacion"):
        return [{"tipo": prop["operacion"], "precio": prop.get("precio"), "moneda": prop.get("moneda") or "MXN"}]
    return []


def caracteristicas_de(prop: dict) -> List[str]:
    if prop.get("caracteristicas"):
        return list(prop["caracteristicas"])
    return clasificar_amenidades(prop.get("amenidades") or [])[0]


def _lista(req: dict, plural: str, singular: str) -> List[str]:
    v = [x for x in (req.get(plural) or []) if x]
    if not v and req.get(singular):
        v = [req[singular]]
    return v


def zonas_de(req: dict) -> List[str]:
    z = [x for x in (req.get("zonas") or []) if x and str(x).strip()]
    if not z:
        z = [x for x in (req.get("colonia"), req.get("ciudad")) if x and str(x).strip()]
    return [normaliza(x) for x in z if normaliza(x)]


def coincide(req: dict, prop: dict) -> Tuple[bool, List[str]]:
    """(¿coincide?, motivos legibles). Todo criterio vacío se ignora."""
    motivos: List[str] = []
    if (prop.get("estatus") or "activa") != "activa" or prop.get("archivada"):
        return False, ["no está activo"]

    ops_req = _lista(req, "operaciones", "operacion")
    ops = operaciones_de(prop)
    elegidas = [o for o in ops if not ops_req or o.get("tipo") in ops_req]
    if not elegidas:
        return False, ["operación distinta"]

    tipos = _lista(req, "tipos", "tipo_inmueble")
    if tipos:
        sub, fam = prop.get("subtipo") or prop.get("tipo"), prop.get("tipo")
        # Un tipo general del requerimiento ("casa") acepta sus variantes
        # (casa en condominio, villa…); uno específico, sólo ese.
        if not any(t == sub or (t == fam and tipo_familia(t) == t) for t in tipos):
            return False, ["tipo distinto"]

    zonas = zonas_de(req)
    if zonas:
        lugar = " | ".join(normaliza(prop.get(k)) for k in ("colonia", "ciudad", "estado"))
        if not any(z in lugar for z in zonas):
            return False, ["fuera de la zona"]
        motivos.append("en la zona")

    pmin, pmax = _num(req.get("precio_min")), _num(req.get("precio_max"))
    if pmin or pmax:
        moneda = (req.get("moneda") or "MXN").upper()
        en_rango = False
        for o in elegidas:
            precio = _num(o.get("precio"))
            if precio is None or (o.get("moneda") or "MXN").upper() != moneda:
                continue
            if (not pmin or precio >= pmin) and (not pmax or precio <= pmax):
                en_rango = True
                break
        if not en_rango:
            return False, ["fuera de presupuesto"]
        motivos.append("en presupuesto")

    for campo_req, campo_prop, etiqueta in (("recamaras_min", "recamaras", "recámaras"),
                                            ("banos_min", "banos", "baños"),
                                            ("estacionamientos_min", "estacionamientos", "estacionamientos")):
        minimo = _num(req.get(campo_req))
        if minimo and (_num(prop.get(campo_prop)) or 0) < minimo:
            return False, [f"menos {etiqueta}"]

    for base in ("m2_construccion", "m2_terreno"):
        lo, hi, valor = _num(req.get(base + "_min")), _num(req.get(base + "_max")), _num(prop.get(base))
        if (lo or hi) and (valor is None or (lo and valor < lo) or (hi and valor > hi)):
            return False, ["superficie distinta"]

    pedidas = [c for c in (req.get("caracteristicas") or []) if c]
    if pedidas:
        tiene = set(caracteristicas_de(prop))
        faltan = [c for c in pedidas if c not in tiene]
        if faltan:
            return False, ["le faltan características"]
        motivos.append("con lo que pide")

    if req.get("solo_comision_compartida") and not (prop.get("comision_compartida") is True or prop.get("en_bolsa")):
        return False, ["no comparte comisión"]

    return True, motivos or ["coincide"]


def puntaje(req: dict, prop: dict) -> int:
    """Para ordenar: más criterios cumplidos y más reciente, primero."""
    _, motivos = coincide(req, prop)
    return len(motivos) * 10 + (5 if prop.get("fotos") else 0)


SELECT_PROPIEDADES = ("id,user_id,org_id,asignado_a,titulo,tipo,subtipo,operacion,precio,moneda,operaciones,"
                      "estatus,archivada,colonia,ciudad,estado,recamaras,banos,estacionamientos,m2_construccion,"
                      "m2_terreno,caracteristicas,amenidades,comision_compartida,en_bolsa,bolsa_comision,fotos,"
                      "created_at,updated_at")
