"""Publish a Broquer property to the connected Facebook Page."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.facebook_connection_store import get_facebook_meta_row
from core.facebook_graph import _fb_exigir_ok, _fb_request

router = APIRouter()


@router.post("/facebook/publish-property")
async def facebook_publish_property(request: Request):
    """Publica una propiedad en Facebook usando el token guardado del usuario."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")

    body = await request.json()
    titulo = body.get("titulo", "Nueva propiedad")
    precio = body.get("precio", "")
    tipo = body.get("tipo", "Inmueble")
    operacion = body.get("operacion", "venta")
    colonia = body.get("colonia", "")
    ciudad = body.get("ciudad", "")
    m2 = body.get("m2_construccion", "")
    recamaras = body.get("recamaras", "")
    fotos = body.get("fotos", [])
    descripcion = body.get("descripcion", "")

    row = await get_facebook_meta_row(user_id)
    meta = row.get("meta") or {}
    page_id = meta.get("page_id", "")
    page_token = row.get("page_token", "")
    if not page_id or not page_token:
        raise HTTPException(
            status_code=400,
            detail="Facebook no conectado. Ve a tu perfil para conectar tu página.",
        )
    facebook = {"page_name": meta.get("page_name", "")}

    precio_fmt = f"${int(precio):,}" if precio else ""
    ubicacion = ", ".join(filter(None, [colonia, ciudad]))
    specs = []
    if m2:
        specs.append(f"🏠 {m2} m²")
    if recamaras:
        specs.append(f"🛏️ {recamaras} rec.")
    specs_str = " · ".join(specs)

    lines = [
        f"{'🏠' if operacion == 'venta' else '🔑'} {tipo} en {operacion.upper()} — {titulo}",
        "",
    ]
    if ubicacion:
        lines.append(f"📍 {ubicacion}")
    if precio_fmt:
        lines.append(f"💰 {precio_fmt} MXN")
    if specs_str:
        lines.append(specs_str)
    if descripcion:
        lines.extend(["", descripcion[:200]])
    lines.extend(["", "✅ Publicado con Broquer"])
    mensaje = "\n".join(lines)

    async with httpx.AsyncClient(timeout=30) as client:
        photo_ids = []
        for url in (fotos or [])[:5]:
            try:
                response = await _fb_request(
                    client,
                    "POST",
                    f"{page_id}/photos",
                    token=page_token,
                    json_body={"url": url, "published": False},
                )
                if response is not None and response.status_code in (200, 201):
                    photo_id = response.json().get("id")
                    if photo_id:
                        photo_ids.append({"media_fbid": photo_id})
            except Exception:
                pass

        payload: dict = {"message": mensaje}
        if photo_ids:
            payload["attached_media"] = photo_ids

        post_response = await _fb_request(
            client,
            "POST",
            f"{page_id}/feed",
            token=page_token,
            json_body=payload,
        )

    data = _fb_exigir_ok(post_response, "Error publicando en Facebook")
    return {
        "ok": True,
        "post_id": data.get("id"),
        "page_name": facebook.get("page_name", ""),
    }
