"""
BROQUER DEMO EN VIVO
────────────────────
Sistema de presentación sin credenciales.

• POST /demo-live/sesion          → crea o devuelve sesión compartida
• GET  /demo-live/estado          → snapshot completo de la sesión
• POST /demo-live/accion          → registra acción visible a todos
• POST /demo-live/avm             → valuación instantánea (precargada)
• POST /demo-live/chat            → Broq IA real pero en contexto demo
• GET  /demo-live/whatsapp        → conversaciones WA ficticias
• POST /demo-live/whatsapp/enviar → simula envío de mensaje WA
• POST /demo-live/contacto/crear  → crea contacto visible a todos
• POST /demo-live/propiedad/crear → crea propiedad visible a todos

Sesiones: 4 horas de vida. Polling de estado cada 3 s en el frontend.
Todos los participantes con el mismo session_id ven los mismos datos.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.config import settings

router = APIRouter(prefix="/demo-live", tags=["demo-live"])

# ─── Almacén en memoria (sessions dict) ───────────────────────────────────────
# Cada sesión vive 4 horas. Se limpia lazy en cada request.
_SESSIONS: dict[str, dict] = {}
_SESSION_TTL = 4 * 3600  # segundos

# ─── Datos ficticios precargados ──────────────────────────────────────────────

_PROPIEDADES_BASE = [
    {
        "id": "p-001",
        "titulo": "Casa residencial en Jardines del Pedregal",
        "tipo": "Casa",
        "operacion": "Venta",
        "precio": 8_500_000,
        "moneda": "MXN",
        "m2_construccion": 320,
        "m2_terreno": 480,
        "recamaras": 4,
        "banos": 3.5,
        "estacionamientos": 2,
        "colonia": "Jardines del Pedregal",
        "ciudad": "Morelia",
        "estado_inmueble": "Disponible",
        "descripcion": "Casa amplia con acabados premium, jardín privado y alberca.",
        "foto": "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=800&q=80",
        "created_at": "2026-08-15T10:30:00Z",
        "vistas": 47,
        "destacada": True,
    },
    {
        "id": "p-002",
        "titulo": "Departamento en Santa María de Guido",
        "tipo": "Departamento",
        "operacion": "Renta",
        "precio": 18_500,
        "moneda": "MXN",
        "m2_construccion": 95,
        "m2_terreno": 0,
        "recamaras": 2,
        "banos": 2,
        "estacionamientos": 1,
        "colonia": "Santa María de Guido",
        "ciudad": "Morelia",
        "estado_inmueble": "Disponible",
        "descripcion": "Departamento moderno, amueblado, vista a la ciudad.",
        "foto": "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800&q=80",
        "created_at": "2026-08-18T14:00:00Z",
        "vistas": 23,
        "destacada": False,
    },
    {
        "id": "p-003",
        "titulo": "Local comercial en Centro Histórico",
        "tipo": "Local",
        "operacion": "Renta",
        "precio": 45_000,
        "moneda": "MXN",
        "m2_construccion": 220,
        "m2_terreno": 220,
        "recamaras": 0,
        "banos": 2,
        "estacionamientos": 4,
        "colonia": "Centro Histórico",
        "ciudad": "Morelia",
        "estado_inmueble": "Disponible",
        "descripcion": "Local en pleno centro, ideal para restaurante o oficinas.",
        "foto": "https://images.unsplash.com/photo-1497366216548-37526070297c?w=800&q=80",
        "created_at": "2026-08-20T09:00:00Z",
        "vistas": 61,
        "destacada": True,
    },
    {
        "id": "p-004",
        "titulo": "Terreno en Lomas de Morelia",
        "tipo": "Terreno",
        "operacion": "Venta",
        "precio": 3_200_000,
        "moneda": "MXN",
        "m2_construccion": 0,
        "m2_terreno": 600,
        "recamaras": 0,
        "banos": 0,
        "estacionamientos": 0,
        "colonia": "Lomas de Morelia",
        "ciudad": "Morelia",
        "estado_inmueble": "Disponible",
        "descripcion": "Terreno plano con todos los servicios, excelente ubicación.",
        "foto": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=800&q=80",
        "created_at": "2026-08-22T11:00:00Z",
        "vistas": 18,
        "destacada": False,
    },
    {
        "id": "p-005",
        "titulo": "Casa en Fraccionamiento Los Olivos",
        "tipo": "Casa",
        "operacion": "Venta",
        "precio": 4_200_000,
        "moneda": "MXN",
        "m2_construccion": 180,
        "m2_terreno": 240,
        "recamaras": 3,
        "banos": 2.5,
        "estacionamientos": 2,
        "colonia": "Los Olivos",
        "ciudad": "Morelia",
        "estado_inmueble": "En proceso",
        "descripcion": "Casa familiar en coto privado con vigilancia 24h.",
        "foto": "https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=800&q=80",
        "created_at": "2026-08-10T16:00:00Z",
        "vistas": 89,
        "destacada": True,
    },
]

_CONTACTOS_BASE = [
    {
        "id": "c-001",
        "nombre": "Martina Reyes Villanueva",
        "telefono": "+52 443 211 9034",
        "email": "martina.reyes@gmail.com",
        "etiqueta": "Comprador activo",
        "fuente": "Referido",
        "estado": "Caliente",
        "notas": "Busca casa 3 recámaras, presupuesto hasta $5M. Necesita escriturar antes de diciembre.",
        "propiedad_interes": "p-005",
        "created_at": "2026-08-20T10:00:00Z",
        "ultima_actividad": "Hace 2 horas",
        "color": "#0A5DE0",
    },
    {
        "id": "c-002",
        "nombre": "Carlos Eduardo Sánchez",
        "telefono": "+52 443 188 7241",
        "email": "cesanchez@outlook.com",
        "etiqueta": "Inversionista",
        "fuente": "Facebook Ads",
        "estado": "Tibio",
        "notas": "Busca locales comerciales para rentar. Tiene capital para 2 propiedades.",
        "propiedad_interes": "p-003",
        "created_at": "2026-08-18T14:30:00Z",
        "ultima_actividad": "Ayer",
        "color": "#0E9F6E",
    },
    {
        "id": "c-003",
        "nombre": "Sofía Gutiérrez Mora",
        "telefono": "+52 443 901 5523",
        "email": "sofia.gtz@empresa.com",
        "etiqueta": "Renta corporativa",
        "fuente": "Sitio web",
        "estado": "Caliente",
        "notas": "Requiere departamento amueblado para ejecutivo de empresa transnacional. Contrato mínimo 12 meses.",
        "propiedad_interes": "p-002",
        "created_at": "2026-08-25T09:15:00Z",
        "ultima_actividad": "Hace 20 min",
        "color": "#D42A62",
    },
    {
        "id": "c-004",
        "nombre": "Alejandro Fuentes Ortiz",
        "telefono": "+52 443 755 3390",
        "email": "afuentes@gmail.com",
        "etiqueta": "Vendedor",
        "fuente": "AMPI",
        "estado": "Activo",
        "notas": "Quiere vender su casa en Pedregal. Precio pedido $9.5M, flexible en $8.5M. Urgente.",
        "propiedad_interes": "p-001",
        "created_at": "2026-08-12T11:00:00Z",
        "ultima_actividad": "3 días",
        "color": "#B34E0B",
    },
    {
        "id": "c-005",
        "nombre": "Daniela Pérez Castro",
        "telefono": "+52 443 622 1178",
        "email": "dperez@correo.com",
        "etiqueta": "Primera vivienda",
        "fuente": "WhatsApp",
        "estado": "Frío",
        "notas": "Pareja joven, crédito Infonavit. Buscan algo hasta $2.5M en zona norte.",
        "propiedad_interes": None,
        "created_at": "2026-08-05T15:45:00Z",
        "ultima_actividad": "1 semana",
        "color": "#57607A",
    },
]

_TAREAS_BASE = [
    {
        "id": "t-001",
        "titulo": "Visita de seguimiento — Martina Reyes",
        "tipo": "Visita",
        "prioridad": "Alta",
        "fecha": "2026-09-03",
        "hora": "11:00",
        "estado": "Pendiente",
        "contacto_id": "c-001",
        "propiedad_id": "p-005",
        "notas": "Llevar planos y tabla comparativa de financiamiento.",
    },
    {
        "id": "t-002",
        "titulo": "Enviar contrato de exclusiva — Alejandro Fuentes",
        "tipo": "Documento",
        "prioridad": "Alta",
        "fecha": "2026-09-02",
        "hora": "09:00",
        "estado": "Vencida",
        "contacto_id": "c-004",
        "propiedad_id": "p-001",
        "notas": "Contrato ya generado, pendiente de firma.",
    },
    {
        "id": "t-003",
        "titulo": "Presentar opciones comerciales — Carlos Sánchez",
        "tipo": "Llamada",
        "prioridad": "Media",
        "fecha": "2026-09-04",
        "hora": "16:30",
        "estado": "Pendiente",
        "contacto_id": "c-002",
        "propiedad_id": "p-003",
        "notas": "Preparar análisis de rentabilidad de 3 locales.",
    },
    {
        "id": "t-004",
        "titulo": "Seguimiento departamento amueblado — Sofía",
        "tipo": "WhatsApp",
        "prioridad": "Alta",
        "fecha": "2026-09-01",
        "hora": "10:00",
        "estado": "Completada",
        "contacto_id": "c-003",
        "propiedad_id": "p-002",
        "notas": "Confirmar fechas de entrada.",
    },
]

_WA_CONVERSACIONES = [
    {
        "id": "wa-001",
        "numero": "+52 443 211 9034",
        "nombre": "Martina Reyes",
        "no_leidos": 2,
        "estado": "Activo",
        "ultimo_mensaje": "Sí, el sábado puedo a las 11. ¿Llevo a mi esposo también?",
        "timestamp": "10:42",
        "mensajes": [
            {"rol": "cliente", "texto": "Hola! Vi la casa de Pedregal en tu Facebook", "hora": "10:15"},
            {"rol": "broq", "texto": "¡Hola Martina! Soy Broq, el asistente de Grupo Navarro 🏠 Qué bueno que te interesó. La casa de Jardines del Pedregal tiene 320m², 4 recámaras, alberca y precio de $8.5M. ¿Quieres que te agende una visita?", "hora": "10:15"},
            {"rol": "cliente", "texto": "Sí me interesa. ¿Tienen algo más barato?", "hora": "10:28"},
            {"rol": "broq", "texto": "Claro, también tenemos una casa en Los Olivos a $4.2M, 3 recámaras, coto privado con vigilancia. ¿Te mando más fotos?", "hora": "10:28"},
            {"rol": "cliente", "texto": "Sí por favor", "hora": "10:30"},
            {"rol": "broq", "texto": "¡Aquí van! También te agendé con nuestro asesor para el sábado. ¿Te funciona a las 11am?", "hora": "10:31"},
            {"rol": "cliente", "texto": "Sí, el sábado puedo a las 11. ¿Llevo a mi esposo también?", "hora": "10:42"},
        ],
    },
    {
        "id": "wa-002",
        "numero": "+52 443 901 5523",
        "nombre": "Sofía Gutiérrez",
        "no_leidos": 0,
        "estado": "Resuelto",
        "ultimo_mensaje": "Perfecto, confirmado para el 1 de septiembre.",
        "timestamp": "Ayer",
        "mensajes": [
            {"rol": "cliente", "texto": "Buenas tardes, busco departamento amueblado para ejecutivo, contrato corporativo", "hora": "17:00"},
            {"rol": "broq", "texto": "Buenas tardes Sofía. Tenemos un departamento en Santa María de Guido, 95m², 2 recámaras, completamente amueblado. Renta $18,500/mes. ¿Le interesa?", "hora": "17:01"},
            {"rol": "cliente", "texto": "Sí. ¿Cuándo podríamos hacer la visita?", "hora": "17:15"},
            {"rol": "cliente", "texto": "Perfecto, confirmado para el 1 de septiembre.", "hora": "18:30"},
        ],
    },
    {
        "id": "wa-003",
        "numero": "+52 443 188 7241",
        "nombre": "Carlos Sánchez",
        "no_leidos": 1,
        "estado": "Activo",
        "ultimo_mensaje": "¿Tienen algo en el centro con estacionamiento?",
        "timestamp": "Lun",
        "mensajes": [
            {"rol": "cliente", "texto": "Hola, busco locales en renta para inversión", "hora": "09:20"},
            {"rol": "broq", "texto": "Hola Carlos! Tenemos un local en el Centro Histórico, 220m², $45,000/mes, con 4 cajones de estacionamiento. Ideal para restaurante u oficinas. ¿Le mando la ficha completa?", "hora": "09:21"},
            {"rol": "cliente", "texto": "¿Tienen algo en el centro con estacionamiento?", "hora": "09:45"},
        ],
    },
]

_AVM_RESULTADO = {
    "valor_estimado": 8_250_000,
    "rango_min": 7_800_000,
    "rango_max": 8_700_000,
    "precio_m2": 25_781,
    "confianza": "Alta",
    "comparables": [
        {"direccion": "Jardines del Pedregal Norte", "precio": 8_100_000, "m2": 310, "precio_m2": 26_129, "distancia": "0.4 km", "fecha": "Jul 2026"},
        {"direccion": "Residencial Pedregal Sur", "precio": 8_900_000, "m2": 340, "precio_m2": 26_176, "distancia": "0.7 km", "fecha": "Jun 2026"},
        {"direccion": "Pedregal de San Ángel", "precio": 7_600_000, "m2": 290, "precio_m2": 26_207, "distancia": "1.1 km", "fecha": "Ago 2026"},
        {"direccion": "Lomas del Pedregal", "precio": 8_350_000, "m2": 325, "precio_m2": 25_692, "distancia": "1.3 km", "fecha": "Jul 2026"},
    ],
    "factores_ajuste": [
        {"factor": "Alberca", "impacto": "+4.2%", "tipo": "positivo"},
        {"factor": "Antigüedad (8 años)", "impacto": "-1.8%", "tipo": "negativo"},
        {"factor": "Acabados premium", "impacto": "+3.1%", "tipo": "positivo"},
        {"factor": "Zona exclusiva", "impacto": "+5.0%", "tipo": "positivo"},
    ],
    "recomendaciones": [
        "Precio de lista sugerido: $8,500,000 MXN para negociación con margen.",
        "El mercado en Pedregal ha mostrado +2.8% de apreciación en los últimos 6 meses.",
        "Tiempo estimado de venta en este rango: 45-75 días.",
    ],
    "resumen_ejecutivo": "La propiedad se ubica en el cuartil superior del mercado para Jardines del Pedregal. Los 4 comparables recientes confirman solidez en el rango $7.8M-$8.7M. Se recomienda lista a $8.5M con flexibilidad hasta $8.1M en negociación.",
    "fuentes": ["Inmuebles24", "Lamudi", "EasyBroker", "Registros públicos Michoacán"],
    "fecha_analisis": datetime.now(timezone.utc).strftime("%d %b %Y"),
}

_ESTADISTICAS = {
    "propiedades_activas": 47,
    "contactos_total": 128,
    "leads_este_mes": 23,
    "citas_semana": 8,
    "comisiones_estimadas": 1_240_000,
    "tasa_cierre": 68,
    "tiempo_promedio_venta": 52,
    "propiedades_por_estado": {
        "Disponible": 38,
        "En proceso": 6,
        "Vendida": 3,
    },
    "leads_por_fuente": {
        "WhatsApp": 41,
        "Facebook Ads": 28,
        "Referidos": 22,
        "Sitio web": 19,
        "AMPI": 18,
    },
    "actividad_semanal": [4, 7, 3, 9, 5, 8, 2],
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ahora() -> float:
    return time.time()

def _ts_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _limpiar_sesiones_viejas():
    ahora = _ahora()
    muertas = [k for k, v in _SESSIONS.items() if ahora - v["created_at"] > _SESSION_TTL]
    for k in muertas:
        del _SESSIONS[k]

def _get_or_create_sesion(session_id: str) -> dict:
    _limpiar_sesiones_viejas()
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = {
            "session_id": session_id,
            "created_at": _ahora(),
            "participantes": 0,
            "propiedades": [dict(p) for p in _PROPIEDADES_BASE],
            "contactos": [dict(c) for c in _CONTACTOS_BASE],
            "tareas": [dict(t) for t in _TAREAS_BASE],
            "wa_conversaciones": [dict(w) for w in _WA_CONVERSACIONES],
            "acciones": [],   # feed de actividad en vivo
            "ultima_actualizacion": _ahora(),
        }
    return _SESSIONS[session_id]

def _registrar_accion(sesion: dict, tipo: str, descripcion: str, datos: dict | None = None):
    accion = {
        "id": str(uuid.uuid4())[:8],
        "tipo": tipo,
        "descripcion": descripcion,
        "datos": datos or {},
        "ts": _ts_iso(),
        "ts_unix": _ahora(),
    }
    sesion["acciones"].insert(0, accion)
    sesion["acciones"] = sesion["acciones"][:50]  # máx 50 acciones en memoria
    sesion["ultima_actualizacion"] = _ahora()


# ─── Modelos ──────────────────────────────────────────────────────────────────

class SesionIn(BaseModel):
    session_id: Optional[str] = None
    nombre_presentador: str = "Chava"

class AccionIn(BaseModel):
    session_id: str
    tipo: str          # "crear_contacto" | "crear_propiedad" | "mensaje_wa" | "custom"
    descripcion: str
    datos: dict = {}

class AvmIn(BaseModel):
    session_id: str
    colonia: str = "Jardines del Pedregal"
    tipo_inmueble: str = "Casa"
    operacion: str = "Venta"
    m2_construccion: float = 320
    m2_terreno: float = 480
    recamaras: int = 4
    banos: float = 3.5
    estacionamientos: int = 2
    ciudad: str = "Morelia"
    comentarios: str = ""

class ChatIn(BaseModel):
    session_id: str
    mensaje: str
    historial: list = []

class WaMensajeIn(BaseModel):
    session_id: str
    conversacion_id: str
    texto: str
    remitente: str = "agente"  # "agente" | "cliente"

class ContactoIn(BaseModel):
    session_id: str
    nombre: str
    telefono: str = ""
    email: str = ""
    etiqueta: str = "Lead"
    fuente: str = "Demo"
    estado: str = "Nuevo"
    notas: str = ""

class PropiedadIn(BaseModel):
    session_id: str
    titulo: str
    tipo: str = "Casa"
    operacion: str = "Venta"
    precio: float = 0
    m2_construccion: float = 0
    m2_terreno: float = 0
    recamaras: int = 0
    banos: float = 0
    colonia: str = ""
    ciudad: str = "Morelia"
    descripcion: str = ""


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/sesion")
async def crear_sesion(body: SesionIn):
    """Crea o recupera una sesión demo. Devuelve el session_id y el estado inicial."""
    sid = body.session_id or hashlib.md5(f"demo-{int(_ahora() / 3600)}".encode()).hexdigest()[:12]
    sesion = _get_or_create_sesion(sid)
    sesion["participantes"] = sesion.get("participantes", 0) + 1
    sesion["presentador"] = body.nombre_presentador
    return {
        "session_id": sid,
        "presentador": body.nombre_presentador,
        "participantes": sesion["participantes"],
        "ttl_segundos": int(_SESSION_TTL - (_ahora() - sesion["created_at"])),
        "ok": True,
    }


@router.get("/estado/{session_id}")
async def estado_sesion(session_id: str, desde: float = 0):
    """
    Snapshot completo de la sesión.
    Si 'desde' > 0, solo devuelve acciones nuevas desde ese timestamp unix.
    """
    if session_id not in _SESSIONS:
        return JSONResponse({"error": "Sesión no encontrada o expirada."}, status_code=404)
    sesion = _SESSIONS[session_id]
    acciones_nuevas = [
        a for a in sesion["acciones"] if a["ts_unix"] > desde
    ] if desde > 0 else sesion["acciones"][:20]
    return {
        "session_id": session_id,
        "propiedades": sesion["propiedades"],
        "contactos": sesion["contactos"],
        "tareas": sesion["tareas"],
        "estadisticas": _ESTADISTICAS,
        "acciones_recientes": acciones_nuevas,
        "ultima_actualizacion": sesion["ultima_actualizacion"],
        "participantes": sesion["participantes"],
        "presentador": sesion.get("presentador", "Asesor"),
    }


@router.post("/accion")
async def registrar_accion(body: AccionIn):
    if body.session_id not in _SESSIONS:
        return JSONResponse({"error": "Sesión no encontrada."}, status_code=404)
    sesion = _SESSIONS[body.session_id]
    _registrar_accion(sesion, body.tipo, body.descripcion, body.datos)
    return {"ok": True, "ts": sesion["ultima_actualizacion"]}


@router.post("/avm")
async def avm_demo(body: AvmIn):
    """
    Valuación instantánea. Simula 1.2 s de 'análisis' con datos reales ficticios
    para la demo. No llama a ninguna API externa.
    """
    await asyncio.sleep(1.2)  # suspense realista
    resultado = dict(_AVM_RESULTADO)
    # Ajuste dinámico menor para que no sea idéntico en cada corrida
    factor = 0.95 + (hash(body.colonia) % 10) * 0.01
    resultado["valor_estimado"] = int(resultado["valor_estimado"] * factor)
    resultado["rango_min"] = int(resultado["rango_min"] * factor)
    resultado["rango_max"] = int(resultado["rango_max"] * factor)
    resultado["precio_m2"] = int(resultado["precio_m2"] * factor)
    resultado["colonia"] = body.colonia
    resultado["tipo_inmueble"] = body.tipo_inmueble
    resultado["m2_construccion"] = body.m2_construccion
    resultado["m2_terreno"] = body.m2_terreno
    resultado["fecha_analisis"] = datetime.now(timezone.utc).strftime("%d %b %Y")
    if body.session_id in _SESSIONS:
        _registrar_accion(
            _SESSIONS[body.session_id],
            "avm",
            f"Valuación generada: {body.colonia} — ${resultado['valor_estimado']:,.0f} MXN",
            {"colonia": body.colonia, "valor": resultado["valor_estimado"]},
        )
    return resultado


@router.post("/chat")
async def chat_demo(body: ChatIn):
    """
    Chat con Broq real de Claude, pero con contexto demo inyectado.
    Usa la API de Anthropic con el system prompt de la demo.
    """
    if not settings.anthropic_api_key:
        return {"respuesta": "Broq está listo para la demo. (Anthropic API key no configurada en este entorno.)", "ok": False}

    sesion = _SESSIONS.get(body.session_id, {})
    n_props = len(sesion.get("propiedades", _PROPIEDADES_BASE))
    n_contactos = len(sesion.get("contactos", _CONTACTOS_BASE))

    system = f"""Eres Broq, el asistente de inteligencia artificial de Broquer — el sistema operativo para agentes inmobiliarios en México.

Estás en una sesión de presentación en vivo. Sé brillante, conciso y útil.

CONTEXTO ACTUAL DE LA DEMO:
- Agencia: Grupo Navarro, Morelia, Michoacán
- Propiedades en cartera: {n_props}
- Contactos activos: {n_contactos}
- Módulos activos: CRM, WhatsApp IA, AVM, Contratos, PLD, ISR, Firmas Electrónicas

Propiedades destacadas disponibles:
1. Casa en Jardines del Pedregal — $8,500,000 MXN — 320m², 4 rec, alberca
2. Departamento en Santa María de Guido — $18,500/mes — 95m², amueblado
3. Local en Centro Histórico — $45,000/mes — 220m², 4 cajones
4. Terreno en Lomas de Morelia — $3,200,000 — 600m²
5. Casa en Los Olivos — $4,200,000 — 180m², coto privado

Responde en español mexicano, de manera profesional pero cercana. Máximo 3 párrafos. 
Si te preguntan algo que puede demostrar una función de Broquer (valuación, contrato, compliance, etc.), explica brevemente cómo lo haría el sistema y ofrece demostrarlo."""

    mensajes = []
    for m in (body.historial or [])[-10:]:
        mensajes.append({"role": m.get("rol", "user"), "content": m.get("texto", "")})
    mensajes.append({"role": "user", "content": body.mensaje})

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{settings.anthropic_base}/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 600,
                    "system": system,
                    "messages": mensajes,
                },
            )
            d = r.json()
            texto = d.get("content", [{}])[0].get("text", "No pude procesar eso. Intenta de nuevo.")
    except Exception as e:
        texto = f"Broq está disponible. (Error de conexión: {str(e)[:80]})"

    if body.session_id in _SESSIONS:
        _registrar_accion(
            _SESSIONS[body.session_id],
            "chat",
            f"Pregunta a Broq: «{body.mensaje[:60]}»",
            {},
        )
    return {"respuesta": texto, "ok": True}


@router.get("/whatsapp/{session_id}")
async def whatsapp_demo(session_id: str):
    if session_id not in _SESSIONS:
        return JSONResponse({"error": "Sesión no encontrada."}, status_code=404)
    sesion = _SESSIONS[session_id]
    return {"conversaciones": sesion["wa_conversaciones"]}


@router.post("/whatsapp/enviar")
async def wa_enviar(body: WaMensajeIn):
    if body.session_id not in _SESSIONS:
        return JSONResponse({"error": "Sesión no encontrada."}, status_code=404)
    sesion = _SESSIONS[body.session_id]
    conv = next((c for c in sesion["wa_conversaciones"] if c["id"] == body.conversacion_id), None)
    if not conv:
        return JSONResponse({"error": "Conversación no encontrada."}, status_code=404)

    hora_actual = datetime.now().strftime("%H:%M")
    nuevo_mensaje = {
        "rol": body.remitente,
        "texto": body.texto,
        "hora": hora_actual,
    }
    conv["mensajes"].append(nuevo_mensaje)
    conv["ultimo_mensaje"] = body.texto[:60]
    conv["timestamp"] = hora_actual
    if body.remitente == "cliente":
        conv["no_leidos"] = conv.get("no_leidos", 0) + 1

    _registrar_accion(
        sesion,
        "whatsapp",
        f"Mensaje WA de {conv['nombre']}: «{body.texto[:50]}»",
        {"conversacion": conv["nombre"], "remitente": body.remitente},
    )

    # Si es mensaje de cliente, simular respuesta Broq automática con IA
    respuesta_broq = None
    if body.remitente == "cliente" and settings.anthropic_api_key:
        try:
            historial_msgs = [
                {"role": "user" if m["rol"] == "cliente" else "assistant", "content": m["texto"]}
                for m in conv["mensajes"][-8:]
                if m.get("texto")
            ]
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    f"{settings.anthropic_base}/messages",
                    headers={
                        "x-api-key": settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-6",
                        "max_tokens": 200,
                        "system": f"Eres Broq, asistente de WhatsApp de Grupo Navarro (agencia inmobiliaria en Morelia). Responde de forma breve, cálida y profesional. Máximo 2 oraciones. Nombre del cliente: {conv['nombre']}.",
                        "messages": historial_msgs,
                    },
                )
                d = r.json()
                respuesta_broq = d.get("content", [{}])[0].get("text", "")
                if respuesta_broq:
                    msg_broq = {"rol": "broq", "texto": respuesta_broq, "hora": datetime.now().strftime("%H:%M")}
                    conv["mensajes"].append(msg_broq)
                    conv["no_leidos"] = 0
                    _registrar_accion(sesion, "broq_wa", f"Broq respondió a {conv['nombre']}", {})
        except Exception:
            pass

    return {"ok": True, "respuesta_broq": respuesta_broq}


@router.post("/contacto/crear")
async def crear_contacto(body: ContactoIn):
    if body.session_id not in _SESSIONS:
        return JSONResponse({"error": "Sesión no encontrada."}, status_code=404)
    sesion = _SESSIONS[body.session_id]
    colores = ["#0A5DE0", "#0E9F6E", "#D42A62", "#B34E0B", "#081C4E"]
    nuevo = {
        "id": f"c-demo-{str(uuid.uuid4())[:6]}",
        "nombre": body.nombre,
        "telefono": body.telefono,
        "email": body.email,
        "etiqueta": body.etiqueta,
        "fuente": body.fuente,
        "estado": body.estado,
        "notas": body.notas,
        "propiedad_interes": None,
        "created_at": _ts_iso(),
        "ultima_actividad": "Ahora",
        "color": colores[len(sesion["contactos"]) % len(colores)],
    }
    sesion["contactos"].insert(0, nuevo)
    _registrar_accion(sesion, "contacto_nuevo", f"Nuevo contacto: {body.nombre}", {"nombre": body.nombre, "fuente": body.fuente})
    return {"ok": True, "contacto": nuevo}


@router.post("/propiedad/crear")
async def crear_propiedad(body: PropiedadIn):
    if body.session_id not in _SESSIONS:
        return JSONResponse({"error": "Sesión no encontrada."}, status_code=404)
    sesion = _SESSIONS[body.session_id]
    fotos_demo = [
        "https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=800&q=80",
        "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800&q=80",
        "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800&q=80",
    ]
    nueva = {
        "id": f"p-demo-{str(uuid.uuid4())[:6]}",
        "titulo": body.titulo,
        "tipo": body.tipo,
        "operacion": body.operacion,
        "precio": body.precio,
        "moneda": "MXN",
        "m2_construccion": body.m2_construccion,
        "m2_terreno": body.m2_terreno,
        "recamaras": body.recamaras,
        "banos": body.banos,
        "estacionamientos": 0,
        "colonia": body.colonia,
        "ciudad": body.ciudad,
        "estado_inmueble": "Disponible",
        "descripcion": body.descripcion,
        "foto": fotos_demo[len(sesion["propiedades"]) % len(fotos_demo)],
        "created_at": _ts_iso(),
        "vistas": 0,
        "destacada": False,
    }
    sesion["propiedades"].insert(0, nueva)
    _registrar_accion(sesion, "propiedad_nueva", f"Nueva propiedad: {body.titulo}", {"tipo": body.tipo, "precio": body.precio})
    return {"ok": True, "propiedad": nueva}
