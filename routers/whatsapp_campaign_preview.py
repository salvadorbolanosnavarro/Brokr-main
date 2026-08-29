from __future__ import annotations


async def wa2_campana_audiencia_core(req, request, *, _numero_visible, _audiencia_campana,
                                     WA2_CAMPANA_TOPE):
    """Cuenta (sin enviar nada) a cuánta gente le llegaría la campaña."""
    _, numero = await _numero_visible(request, req.numero_id)
    audiencia = await _audiencia_campana(numero, (req.etiqueta or "").strip() or None)
    return {"total": len(audiencia), "tope": WA2_CAMPANA_TOPE}
