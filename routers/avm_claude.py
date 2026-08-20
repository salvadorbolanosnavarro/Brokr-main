"""Claude-based AVM opinion endpoint extracted from main.py without behavior changes."""
from __future__ import annotations

import json as _json
import time

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
from core.telemetry import _track_anthropic
from limites import exigir_cupo, exigir_sesion


router = APIRouter()
ANTHROPIC_API_KEY = settings.anthropic_api_key
ANTHROPIC_BASE = "https://api.anthropic.com/v1"


class AvmClaudeRequest(BaseModel):
    # Ubicación
    estado: str
    ciudad: str
    colonia: str = ""
    direccion: str = ""
    tipo_zona: str = ""
    nse: str = ""
    # Inmueble
    tipo: str
    operacion: str = "venta"
    m2_construccion: float = 0
    m2_terreno: float = 0
    recamaras: int = 0
    banos_completos: float = 0
    medios_banos: int = 0
    estacionamientos: int = 0
    nivel_piso: int = 0
    # Estado y acabados
    antiguedad: int = 0
    conservacion: str = "bueno"
    acabados: str = "medio"
    remodelado: bool = False
    descripcion_remodelacion: str = ""
    # Amenidades
    amenidades: list = []
    # Contexto
    precio_lista: float = 0
    motivo_valuacion: str = ""
    comentarios: str = ""


@router.post("/api/avm-claude")
async def avm_claude(req: AvmClaudeRequest, request: Request):
    _uid = await get_user_id_from_token(request)
    exigir_cupo(request, _uid)
    exigir_sesion(request, _uid)
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada en el servidor")
    user_id = await get_user_id_from_token(request)

    tipo_labels = {
        "casa": "Casa habitación", "departamento": "Departamento/Condominio",
        "terreno": "Terreno", "local": "Local comercial",
        "oficina": "Oficina", "bodega": "Bodega/Nave industrial", "edificio": "Edificio"
    }
    conservacion_labels = {
        "excelente": "Excelente / Como nuevo", "bueno": "Bueno",
        "regular": "Regular / Necesita detalles", "malo": "Malo / Requiere remodelación"
    }
    acabados_labels = {
        "lujo": "Lujo / Residencial Plus", "residencial_plus": "Residencial Plus",
        "residencial": "Residencial", "medio": "Estándar / Medio", "economico": "Económico / Interés social"
    }

    partes = []
    partes.append(f"TIPO DE INMUEBLE: {tipo_labels.get(req.tipo, req.tipo)}")
    partes.append(f"OPERACIÓN: {req.operacion.upper()}")
    partes.append(f"\nUBICACIÓN:")
    partes.append(f"  - Estado: {req.estado}")
    partes.append(f"  - Ciudad/Municipio: {req.ciudad}")
    if req.colonia: partes.append(f"  - Colonia/Fraccionamiento: {req.colonia}")
    if req.direccion: partes.append(f"  - Dirección: {req.direccion}")
    if req.tipo_zona: partes.append(f"  - Tipo de zona: {req.tipo_zona}")
    if req.nse: partes.append(f"  - Nivel socioeconómico de la zona: {req.nse}")

    partes.append(f"\nDIMENSIONES:")
    if req.m2_construccion > 0: partes.append(f"  - Superficie construida: {req.m2_construccion} m²")
    if req.m2_terreno > 0: partes.append(f"  - Superficie de terreno: {req.m2_terreno} m²")
    if req.recamaras > 0: partes.append(f"  - Recámaras: {req.recamaras}")
    if req.banos_completos > 0: partes.append(f"  - Baños completos: {req.banos_completos}")
    if req.medios_banos > 0: partes.append(f"  - Medios baños: {req.medios_banos}")
    if req.estacionamientos > 0: partes.append(f"  - Estacionamientos: {req.estacionamientos}")
    if req.nivel_piso > 0: partes.append(f"  - Piso/Nivel: {req.nivel_piso}")

    partes.append(f"\nESTADO DEL INMUEBLE:")
    partes.append(f"  - Antigüedad aproximada: {req.antiguedad} años")
    partes.append(f"  - Estado de conservación: {conservacion_labels.get(req.conservacion, req.conservacion)}")
    partes.append(f"  - Calidad de acabados: {acabados_labels.get(req.acabados, req.acabados)}")
    if req.remodelado:
        partes.append(f"  - Remodelado recientemente: SÍ")
        if req.descripcion_remodelacion:
            partes.append(f"  - Descripción remodelación: {req.descripcion_remodelacion}")

    if req.amenidades:
        amenidad_labels = {
            "alberca": "Alberca/Pool", "jardin": "Jardín", "bodega": "Bodega",
            "cuarto_servicio": "Cuarto de servicio", "elevador": "Elevador",
            "seguridad": "Seguridad/Vigilancia 24h", "gimnasio": "Gimnasio",
            "salon": "Salón de eventos", "roof_garden": "Roof garden",
            "terraza": "Terraza", "vista": "Vista panorámica", "acceso_playa": "Acceso a playa",
        }
        am_list = [amenidad_labels.get(a, a) for a in req.amenidades]
        partes.append(f"\nAMENIDADES: {', '.join(am_list)}")

    if req.precio_lista > 0:
        partes.append(f"\nPRECIO DE LISTA ACTUAL: ${req.precio_lista:,.0f} MXN")
    if req.motivo_valuacion:
        partes.append(f"MOTIVO DE LA VALUACIÓN: {req.motivo_valuacion}")
    if req.comentarios:
        partes.append(f"COMENTARIOS ADICIONALES: {req.comentarios}")

    descripcion = "\n".join(partes)

    system_prompt = """Eres el mejor perito valuador de bienes raíces de México, certificado por la Sociedad Hipotecaria Federal y el INDAABIN, con 30 años de experiencia valuando propiedades en todo el territorio nacional. Tu análisis es utilizado por bancos, notarías y juzgados para transacciones de millones de pesos. La vida financiera del usuario que solicita esta estimación de valor depende de la precisión de tu análisis.

Tu misión: proporcionar la estimación de valor más precisa, fundamentada y útil posible basándote en:
1. Tu conocimiento profundo del mercado inmobiliario mexicano por región, ciudad y colonia
2. Tendencias y precios actuales del mercado (hasta tu fecha de corte de conocimiento)
3. Factores macroeconómicos: inflación, tasas de interés, INPP, INPC
4. El Método Comparativo de Mercado (enfoque principal)
5. El Enfoque Físico o de Costos (edificaciones)
6. El Enfoque de Capitalización de Rentas (cuando aplique)
7. Ajustes hedónicos por ubicación, características, estado y acabados

IMPORTANTE: Responde ÚNICAMENTE con un objeto JSON válido (sin texto antes ni después, sin markdown, sin ```json), con exactamente esta estructura:
{
  "valor_estimado": <número en pesos MXN sin comas ni signos>,
  "valor_minimo": <número>,
  "valor_maximo": <número>,
  "valor_por_m2_construccion": <número o 0 si no aplica>,
  "valor_por_m2_terreno": <número o 0 si no aplica>,
  "nivel_confianza": "<alta|media|baja>",
  "razon_confianza": "<por qué ese nivel>",
  "resumen_ejecutivo": "<2-3 oraciones concretas sobre el valor>",
  "analisis_ubicacion": "<análisis del valor de la zona y su impacto>",
  "analisis_propiedad": "<análisis de las características físicas y su impacto>",
  "factores_positivos": ["<factor 1>", "<factor 2>", ...],
  "factores_negativos": ["<factor 1>", "<factor 2>", ...],
  "recomendaciones": ["<recomendación 1>", "<recomendación 2>", ...],
  "mercado_actual": "<descripción del mercado actual en esa zona>",
  "metodologia": "<metodología aplicada y justificación>",
  "advertencias": "<advertencias o limitaciones de esta estimación>"
}"""

    user_msg = f"""Por favor valúa la siguiente propiedad y proporciona tu estimación de valor profesional:

{descripcion}

Recuerda: responde ÚNICAMENTE con el JSON, sin ningún texto adicional."""

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 2000,
                "temperature": 0.3,
                "messages": [{"role": "user", "content": user_msg}],
                "system": system_prompt,
            },
        )

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Error de Claude: {r.text[:300]}")

    _resp_json = r.json()
    _track_anthropic(user_id, "avm", "/api/avm-claude", _resp_json,
                     modelo=_resp_json.get("model") or "claude-sonnet-4-6")
    raw = _resp_json.get("content", [{}])[0].get("text", "")
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()

    try:
        resultado = _json.loads(raw)
    except Exception:
        raise HTTPException(status_code=502, detail=f"Claude no devolvió JSON válido: {raw[:500]}")

    resultado["timestamp"] = time.strftime("%Y-%m-%d %H:%M")
    resultado["propiedad_descripcion"] = f"{tipo_labels.get(req.tipo, req.tipo)} en {req.colonia or req.ciudad}, {req.estado}"
    return resultado
