"""Alertas del ciclo del aviso PLD (inmuebles).

Broquer no puede subir el aviso al SPPLD ni consultar su resultado: el SAT no
ofrece una conexión para eso. Lo que sí puede es no dejar que el agente se
olvide de ningún paso. Estas alertas se pintan arriba del módulo de
Cumplimiento y, las urgentes, también llegan como notificación al celular.

Pasos del ciclo:
  1. Completar los datos de las operaciones que generan aviso.
  2. Generar el aviso en Broquer.
  3. Descargar el XML y subirlo al portal del SAT (SPPLD) con la e.firma.
  4. Marcar "Ya lo subí".
  5. Registrar el resultado: acuse con folio (aceptado) o rechazo.

Sin estado y sin base de datos: todo entra por parámetros.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Dict, List

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")

# Días que el SAT suele tardar en reflejar el resultado de un aviso subido.
DIAS_REVISION_SAT = 2

PASOS = [
    "Completa los datos de las operaciones que generan aviso",
    "Genera el aviso en Broquer",
    "Descarga el XML y súbelo al portal del SAT con tu e.firma",
    "Marca «Ya lo subí»",
    "Registra el acuse con su folio, o el rechazo si el SAT no lo aceptó",
]


def mes_de(periodo: str) -> str:
    try:
        anio, mes = str(periodo or "")[:7].split("-")
        return f"{MESES[int(mes) - 1]} {anio}"
    except (ValueError, IndexError):
        return str(periodo or "")


def _fecha(v) -> date | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError:
            return None


def _larga(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]}"


def _plazo(dias: int) -> str:
    if dias < 0:
        return f"venció hace {-dias} día{'s' if dias != -1 else ''}"
    if dias == 0:
        return "vence hoy"
    if dias == 1:
        return "vence mañana"
    return f"vence en {dias} días"


def alertas_pld(cfg: dict, hoy: date, pendientes: List[dict], avisos: List[dict],
                inusuales: List[dict], fecha_limite: Callable[[str, int], date]) -> List[dict]:
    """Lista de alertas, las más urgentes primero.

    Cada alerta: clave (para no repetir el push el mismo día), nivel
    (urgente | aviso | info), titulo, detalle, paso (1-5) y push (bool).
    """
    previo = int(cfg.get("dias_aviso_previo") or 7)
    dia = int(cfg.get("dia_limite_aviso") or 17)
    salida: List[dict] = []

    # 1-2. Operaciones que generan aviso y todavía no están en un aviso.
    por_periodo: Dict[str, int] = {}
    for o in pendientes:
        p = str(o.get("fecha_operacion") or "")[:7]
        if p:
            por_periodo[p] = por_periodo.get(p, 0) + 1
    for p, n in sorted(por_periodo.items()):
        limite = fecha_limite(p, dia)
        dias = (limite - hoy).days
        urgente = dias <= previo
        salida.append({
            "clave": f"periodo:{p}", "nivel": "urgente" if urgente else "aviso", "paso": 1,
            "titulo": f"Aviso de {mes_de(p)}: {_plazo(dias)}",
            "detalle": (f"{n} operación{'es' if n != 1 else ''} genera{'n' if n != 1 else ''} aviso. "
                        f"Completa sus datos, genera el aviso y súbelo al portal del SAT antes del "
                        f"{_larga(limite)}."),
            "push": urgente,
        })

    for a in avisos:
        est = a.get("estatus")
        periodo = a.get("periodo") or ""
        nombre = ("aviso modificatorio" if a.get("tipo") == "modificatorio" else "aviso") + f" de {mes_de(periodo)}"
        if est in ("descartado", "presentado"):
            continue
        if est in ("generado", "borrador") and a.get("formato") != "INM":
            salida.append({
                "clave": f"formato:{a.get('id')}", "nivel": "urgente", "paso": 2,
                "titulo": f"El {nombre} tiene el formato anterior",
                "detalle": "No lo subas: el SAT lo rechazaría. Tócale «Rehacer aviso», completa los "
                           "datos que te pida y vuelve a generarlo.",
                "push": True,
            })
            continue
        if est == "generado":
            limite = fecha_limite(periodo, dia) if a.get("tipo") != "modificatorio" else None
            dias = (limite - hoy).days if limite else None
            urgente = dias is not None and dias <= previo
            salida.append({
                "clave": f"subir:{a.get('id')}", "nivel": "urgente" if urgente else "aviso", "paso": 3,
                "titulo": f"Sube tu {nombre} al portal del SAT"
                          + (f" ({_plazo(dias)})" if dias is not None else ""),
                "detalle": "Descarga el XML, entra al SPPLD con tu e.firma, súbelo y después marca "
                           "«Ya lo subí» aquí.",
                "push": urgente,
            })
        elif est == "subido":
            subido = _fecha(a.get("subido_at"))
            dias = (hoy - subido).days if subido else 0
            vencido = dias >= DIAS_REVISION_SAT
            salida.append({
                "clave": f"acuse:{a.get('id')}", "nivel": "urgente" if vencido else "info", "paso": 5,
                "titulo": f"Revisa en el portal del SAT tu {nombre}",
                "detalle": "Confirma si el SAT lo aceptó y registra aquí el acuse con su folio, o el "
                           "rechazo con el motivo para corregirlo.",
                "push": vencido,
            })
        elif est == "rechazado":
            salida.append({
                "clave": f"rechazo:{a.get('id')}", "nivel": "aviso", "paso": 1,
                "titulo": f"El SAT rechazó tu {nombre}",
                "detalle": ((a.get("motivo_rechazo") or "").strip() + " " if a.get("motivo_rechazo") else "")
                           + "Corrige los datos de la operación y vuelve a generar el aviso.",
                "push": False,
            })

    # Operaciones inusuales: aviso en 24 horas.
    for o in inusuales:
        detectada = o.get("inusual_detectada_at")
        salida.append({
            "clave": f"inusual:{o.get('id')}", "nivel": "urgente", "paso": 1,
            "titulo": "Operación inusual: aviso en 24 horas",
            "detalle": "Genera el aviso de 24 horas con alerta y súbelo al portal del SAT"
                       + (f" (detectada el {_larga(_fecha(detectada))})." if _fecha(detectada) else "."),
            "push": True,
        })

    orden = {"urgente": 0, "aviso": 1, "info": 2}
    salida.sort(key=lambda x: orden.get(x["nivel"], 3))
    return salida
