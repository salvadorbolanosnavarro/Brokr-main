"""Pure WhatsApp training policy and prompt helpers.

This module deliberately contains no database, Meta, or Anthropic I/O.  It is
safe to characterize independently from the root WhatsApp router while that
monolith is decomposed.
"""
from __future__ import annotations

from routers.whatsapp_time import _hora_local


TRAINING_DEFAULTS = {
    "tono": "cálido y profesional",
    "puede": "resolver dudas del inmueble, mandar fotos y precio, y proponer visitas",
    "debe": "preguntar presupuesto, forma de pago y para cuándo busca",
    "no_debe": "inventar direcciones exactas o precios que no existan en el catálogo",
    "especialidad": "",
    "conocimiento": "",
    "objetivo": "calificar al prospecto y agendar una visita",
    "datos_calificar": ["presupuesto", "forma de pago", "para cuándo busca", "zona de interés"],
    "preguntas_extra": [],
    "escalar_palabras": ["quiero hablar con una persona", "hablar con alguien", "es urgente"],
    "horario_activo": False,
    "hora_inicio": "08:00",
    "hora_fin": "21:00",
    "fuera_horario_msg": None,
    "max_mensajes_ia": 0,
    "activo": True,
    "zona_horaria": "America/Mexico_City",
    "modo_ia": "siempre_encendida",
    "pausa_al_responder": True,
    "pausa_duracion_min": 0,
    "nuevos_meses": 3,
}


def _reglas_para_prompt(e: dict) -> str:
    partes = []
    if e.get("puede"): partes.append(f"Puedes: {e['puede']}.")
    if e.get("debe"): partes.append(f"Debes: {e['debe']}.")
    if e.get("no_debe"): partes.append(f"Nunca: {e['no_debe']}.")
    if e.get("preguntas_extra"):
        preguntas = e["preguntas_extra"] if isinstance(e["preguntas_extra"], list) else []
        if preguntas:
            partes.append("Además pregunta cuando venga al caso: " + "; ".join(preguntas) + ".")
    return " ".join(partes)


def _conocimiento_para_prompt(e: dict) -> str:
    """Return the agent-provided business knowledge block for the AI prompt."""
    txt = (e.get("conocimiento") or "").strip()
    if not txt:
        return ""
    return ("INFORMACIÓN DEL NEGOCIO (fuente de verdad, úsala tal cual y NUNCA la contradigas):\n"
            f"{txt[:6000]}\n")


def _calificacion_para_prompt(e: dict) -> str:
    datos = e.get("datos_calificar") or TRAINING_DEFAULTS["datos_calificar"]
    if isinstance(datos, str):
        datos = [d.strip() for d in datos.split(",") if d.strip()]
    return ", ".join(datos) if datos else "presupuesto, forma de pago y para cuándo busca"


def _en_horario(e: dict) -> bool:
    if not e.get("horario_activo"):
        return True
    try:
        ahora = _hora_local(e.get("zona_horaria")).strftime("%H:%M")
        return e.get("hora_inicio", "08:00") <= ahora <= e.get("hora_fin", "21:00")
    except Exception:
        return True
