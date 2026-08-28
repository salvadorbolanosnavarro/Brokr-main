"""Canonical WhatsApp 2.0 agenda and advisor identity helpers."""
from __future__ import annotations


async def _agenda_upsert_core(
    user_id: str,
    numero_id: str,
    telefono: str,
    nombre: str | None = None,
    conocido: bool | None = None,
    *,
    sb_get,
    _now,
    sb_patch,
    sb_post,
    log,
) -> None:
    """Agenda del celular del asesor (wa2_agenda): el nombre con el que ÉL tiene
    registrada a cada persona y si ya la conocía de antes de conectar el número.
    Nunca truena el webhook: la agenda es un apoyo, no la fuente de verdad."""
    try:
        rows = await sb_get("wa2_agenda", {"numero_id": f"eq.{numero_id}",
                                           "telefono": f"eq.{telefono}", "select": "*", "limit": "1"})
        if rows:
            cambios = {"updated_at": _now()}
            if nombre:
                cambios["nombre"] = nombre
            if conocido is not None:
                cambios["conocido"] = conocido
            await sb_patch("wa2_agenda", {"id": f"eq.{rows[0]['id']}"}, cambios)
        else:
            await sb_post("wa2_agenda", {"user_id": user_id, "numero_id": numero_id,
                                         "telefono": telefono, "nombre": nombre,
                                         "conocido": bool(conocido),
                                         "created_at": _now(), "updated_at": _now()})
    except Exception as e:
        log.warning("wa2_agenda no se pudo actualizar (%s): %s", telefono, e)


def _solo_digitos_core(t: str, *, re) -> str:
    return re.sub(r"\D", "", t or "")


def _es_asesor_core(numero: dict, wa_id: str, *, _normaliza_mx) -> bool:
    """True si quien escribe es el DUEÑO del número de Broquer, escribiendo
    desde su NÚMERO PERSONAL registrado (en coexistencia no es posible mandarse
    mensajes a uno mismo, así que el asesor registra su celular personal y desde
    ahí le habla a Broq). Se comparan los últimos 10 dígitos para brincarse el
    lío 52/521. También cubre el caso teórico de un auto-mensaje directo."""
    ajeno = _normaliza_mx(wa_id or "")
    if len(ajeno) < 10:
        return False
    for campo in ("numero_personal", "phone_number"):
        propio = _normaliza_mx((numero or {}).get(campo) or "")
        if propio and propio[-10:] == ajeno[-10:]:
            return True
    return False
