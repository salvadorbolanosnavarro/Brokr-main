from __future__ import annotations


def variables_para(contacto: dict, variables: list) -> list:
    """Sustituye el comodín {nombre} por el primer nombre real del contacto —
    la única personalización automática de la capa estándar."""
    listas = []
    for v in variables:
        if str(v).strip().lower() in ("{nombre}", "{{nombre}}"):
            primero = (contacto.get("nombre") or "").strip().split(" ")[0]
            listas.append(primero.title() if primero else "Hola")
        else:
            listas.append(str(v))
    return listas
