#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise RuntimeError(f"{path}: expected one exact match, found {source.count(old)}")
    target.write_text(source.replace(old, new, 1), encoding="utf-8")


replace_once(
    "routers/staging.py",
    "from pydantic import BaseModel\nfrom PIL import Image, ImageDraw, ImageFont\n\nfrom limites import exigir_cupo, exigir_sesion\n",
    "from pydantic import BaseModel\nfrom PIL import Image, ImageDraw, ImageFont\n\nfrom core.http import fetch_public_bytes\nfrom limites import exigir_cupo, exigir_sesion\n",
)
replace_once(
    "routers/staging.py",
    'SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY',
    'SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")',
)
replace_once(
    "routers/staging.py",
    'if not isinstance(body.foto_url, str) or not body.foto_url.startswith("http"):',
    'if not isinstance(body.foto_url, str) or not body.foto_url.startswith(("http://", "https://")):',
)
replace_once(
    "routers/staging.py",
    '''    # 1) Bajar la foto original.\n    try:\n        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:\n            r = await c.get(body.foto_url)\n        if r.status_code != 200 or not r.content:\n            raise RuntimeError("status " + str(r.status_code))\n        original = r.content\n    except Exception as e:\n        log.warning("[staging] no se pudo bajar la foto: %s", e)\n        raise HTTPException(400, "No se pudo leer la foto original.")\n''',
    '''    # 1) Bajar la foto original sin permitir destinos privados, locales ni redirects inseguros.\n    try:\n        original = await fetch_public_bytes(\n            body.foto_url,\n            timeout=30,\n            max_bytes=20 * 1024 * 1024,\n            max_redirects=3,\n        )\n        if not original:\n            raise RuntimeError("respuesta vacía")\n    except Exception as e:\n        log.warning("[staging] no se pudo bajar la foto: %s", e)\n        raise HTTPException(400, "No se pudo leer la foto original.")\n''',
)

replace_once(
    "routers/organizaciones.py",
    '''        if r.status_code != 200:\n            return []\n        return r.json()\n''',
    '''        if r.status_code != 200:\n            raise HTTPException(\n                status_code=503,\n                detail="No se pudo verificar la organización en este momento.",\n            )\n        return r.json()\n''',
)

replace_once(
    "routers/whatsapp_chatgpt.py",
    'SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_ANON_KEY',
    'SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")',
)
replace_once(
    "routers/whatsapp_chatgpt.py",
    'WA_REGISTER_PIN = os.environ.get("WA_REGISTER_PIN", "123456")',
    'WA_REGISTER_PIN = os.environ.get("WA_REGISTER_PIN", "").strip()',
)
replace_once(
    "routers/whatsapp_chatgpt.py",
    '''        registered = False\n        register_warning = ""\n        if req.register_number:\n            reg_r = await c.post(f"{GRAPH_API}/{phone_number_id}/register", params={"access_token": access_token}, json={"messaging_product": "whatsapp", "pin": WA_REGISTER_PIN})\n''',
    '''        registered = False\n        register_warning = ""\n        if req.register_number:\n            if not WA_REGISTER_PIN:\n                raise HTTPException(status_code=500, detail="WA_REGISTER_PIN no configurado.")\n            reg_r = await c.post(f"{GRAPH_API}/{phone_number_id}/register", params={"access_token": access_token}, json={"messaging_product": "whatsapp", "pin": WA_REGISTER_PIN})\n''',
)

replace_once(
    "whatsapp.py",
    'SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY',
    'SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")',
)
replace_once(
    "whatsapp.py",
    'WA2_VERIFY_TOKEN = os.environ.get("WA2_VERIFY_TOKEN", "broquer2_verify")',
    'WA2_VERIFY_TOKEN = os.environ.get("WA2_VERIFY_TOKEN", "").strip()',
)
replace_once(
    "whatsapp.py",
    'WA2_REGISTER_PIN = os.environ.get("WA_REGISTER_PIN", "142857")',
    'WA2_REGISTER_PIN = os.environ.get("WA_REGISTER_PIN", "").strip()',
)
replace_once(
    "whatsapp.py",
    '''@router.get("/webhook")\nasync def meta_verify(request: Request):\n    p = request.query_params\n    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == WA2_VERIFY_TOKEN:\n        return PlainTextResponse(p.get("hub.challenge", ""))\n    return PlainTextResponse("Forbidden", status_code=403)\n''',
    '''@router.get("/webhook")\nasync def meta_verify(request: Request):\n    if not WA2_VERIFY_TOKEN:\n        return PlainTextResponse("Webhook verification is not configured", status_code=503)\n    p = request.query_params\n    if p.get("hub.mode") == "subscribe" and secrets.compare_digest(\n        p.get("hub.verify_token", ""), WA2_VERIFY_TOKEN\n    ):\n        return PlainTextResponse(p.get("hub.challenge", ""))\n    return PlainTextResponse("Forbidden", status_code=403)\n''',
)
replace_once(
    "whatsapp.py",
    '''        if registrar_numero:\n            rr = await c.post(f"{GRAPH}/{phone_id}/register", headers=h,\n                             json={"messaging_product": "whatsapp", "pin": WA2_REGISTER_PIN})\n''',
    '''        if registrar_numero:\n            if not WA2_REGISTER_PIN:\n                raise HTTPException(status_code=500, detail="WA_REGISTER_PIN no configurado.")\n            rr = await c.post(f"{GRAPH}/{phone_id}/register", headers=h,\n                             json={"messaging_product": "whatsapp", "pin": WA2_REGISTER_PIN})\n''',
)

replace_once(
    "routers/firmas.py",
    'SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY',
    'SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")',
)

print("security hardening applied")
