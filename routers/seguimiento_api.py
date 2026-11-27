"""API del Seguimiento automático (piloto privado, solo cuentas autorizadas)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from core.auth import require_user_id
from core.config import settings
from routers.seguimiento_calientes import calientes
from routers.seguimiento_datos import (actualizar, ajustes_de, borrar, crear, en_lista, es_piloto, guardar, leer,
                                       log, usuario_piloto, usuarios_piloto)
from routers.seguimiento_envio import zona_de
from routers.seguimiento_motor import bucle, ciclo_usuario
from routers.seguimiento_schema import (AjustesReq, InscribirReq, InscripcionPatchReq, SecuenciaPatchReq,
                                        SecuenciaReq, inicio_del_dia_utc, limpiar_ajustes, limpiar_pasos,
                                        limpiar_secuencia, programar)


router = APIRouter(prefix="/seguimiento", tags=["seguimiento"])


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


async def _secuencia(user_id: str, secuencia_id: str) -> dict:
    filas = await leer("seg_secuencias", {"id": f"eq.{secuencia_id}", "user_id": f"eq.{user_id}",
                                          "select": "*", "limit": "1"})
    if not filas:
        raise HTTPException(status_code=404, detail="Secuencia no encontrada.")
    return filas[0]


async def _numero_propio(user_id: str, numero_id: str) -> None:
    filas = await leer("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": f"eq.{user_id}",
                                       "select": "id", "limit": "1"})
    if not filas:
        raise HTTPException(status_code=400, detail="Ese número de WhatsApp no es de tu cuenta.")


async def _nombres(ids) -> dict[str, dict]:
    ids = list({i for i in ids if i})
    salida: dict[str, dict] = {}
    for i in range(0, len(ids), 150):
        for c in await leer("wa2_contactos", {"id": en_lista(ids[i:i + 150]), "select": "id,nombre,wa_id"}):
            salida[c["id"]] = c
    return salida


def _nombre(c: dict | None) -> str:
    c = c or {}
    return (c.get("nombre") or "").strip() or c.get("wa_id") or "Sin nombre"


@router.get("/acceso")
async def acceso(request: Request):
    user_id = await require_user_id(request, detail="Inicia sesión.")
    return {"piloto": es_piloto(user_id)}


@router.get("/resumen")
async def resumen(request: Request):
    user_id = await usuario_piloto(request)
    ahora = _ahora()
    semana = (ahora - timedelta(days=7)).isoformat()
    inscripciones = await leer("seg_inscripciones", {"user_id": f"eq.{user_id}",
                                                     "select": "contacto_id,estado,respondio_en", "limit": "5000"})
    envios = await leer("seg_envios", {"user_id": f"eq.{user_id}", "created_at": f"gte.{semana}",
                                       "select": "contacto_id,tipo,plantilla,estado,error,created_at",
                                       "order": "created_at.desc", "limit": "1000"})
    hoy = inicio_del_dia_utc(ahora, await zona_de(user_id))
    enviados7 = [e for e in envios if e["estado"] == "enviado"]
    respondieron = [i for i in inscripciones if i["estado"] == "respondio" and (i.get("respondio_en") or "") >= semana]
    contactos_tocados = {e["contacto_id"] for e in enviados7}
    recientes = envios[:15]
    nombres = await _nombres([e["contacto_id"] for e in recientes] + [i["contacto_id"] for i in respondieron])
    return {
        "kpis": {
            "activos": sum(1 for i in inscripciones if i["estado"] == "activa"),
            "enviados_hoy": sum(1 for e in enviados7 if e["created_at"] >= hoy.isoformat()),
            "enviados_7d": len(enviados7),
            "respondieron_7d": len(respondieron),
            "tasa_respuesta": round(100 * len(respondieron) / len(contactos_tocados)) if contactos_tocados else None,
        },
        "calientes": await calientes(user_id),
        "respuestas": [{"contacto_id": i["contacto_id"], "nombre": _nombre(nombres.get(i["contacto_id"])),
                        "respondio_en": i.get("respondio_en")} for i in
                       sorted(respondieron, key=lambda x: x.get("respondio_en") or "", reverse=True)[:10]],
        "actividad": [{**e, "nombre": _nombre(nombres.get(e["contacto_id"]))} for e in recientes],
    }


@router.get("/secuencias")
async def secuencias(request: Request):
    user_id = await usuario_piloto(request)
    filas = await leer("seg_secuencias", {"user_id": f"eq.{user_id}", "select": "*", "order": "created_at.desc"})
    conteo: dict[str, dict[str, int]] = {}
    for i in await leer("seg_inscripciones", {"user_id": f"eq.{user_id}", "select": "secuencia_id,estado",
                                              "limit": "10000"}):
        por = conteo.setdefault(i["secuencia_id"], {})
        por[i["estado"]] = por.get(i["estado"], 0) + 1
    for s in filas:
        s["conteo"] = conteo.get(s["id"], {})
    return {"secuencias": filas}


@router.post("/secuencias")
async def crear_secuencia(req: SecuenciaReq, request: Request):
    user_id = await usuario_piloto(request)
    datos = limpiar_secuencia(req)
    await _numero_propio(user_id, datos["numero_id"])
    filas = await crear("seg_secuencias", {**datos, "user_id": user_id})
    if not filas:
        raise HTTPException(status_code=502, detail="No se pudo crear la secuencia.")
    return {"secuencia": filas[0]}


@router.patch("/secuencias/{secuencia_id}")
async def editar_secuencia(secuencia_id: str, req: SecuenciaPatchReq, request: Request):
    user_id = await usuario_piloto(request)
    await _secuencia(user_id, secuencia_id)
    cambios: dict = {"updated_at": _ahora().isoformat()}
    if req.nombre is not None:
        if not req.nombre.strip():
            raise HTTPException(status_code=400, detail="Ponle nombre a la secuencia.")
        cambios["nombre"] = req.nombre.strip()[:80]
    if req.activa is not None:
        cambios["activa"] = req.activa
    if req.auto_leads_nuevos is not None:
        cambios["auto_leads_nuevos"] = req.auto_leads_nuevos
    if req.hora_envio is not None:
        cambios["hora_envio"] = max(7, min(21, int(req.hora_envio)))
    if req.pasos is not None:
        cambios["pasos"] = limpiar_pasos(req.pasos)
    filas = await actualizar("seg_secuencias", {"id": f"eq.{secuencia_id}", "user_id": f"eq.{user_id}"}, cambios)
    return {"secuencia": filas[0] if filas else None}


@router.delete("/secuencias/{secuencia_id}")
async def borrar_secuencia(secuencia_id: str, request: Request):
    user_id = await usuario_piloto(request)
    await _secuencia(user_id, secuencia_id)
    await borrar("seg_secuencias", {"id": f"eq.{secuencia_id}", "user_id": f"eq.{user_id}"})
    return {"ok": True}


@router.get("/secuencias/{secuencia_id}/inscripciones")
async def inscripciones(secuencia_id: str, request: Request):
    user_id = await usuario_piloto(request)
    await _secuencia(user_id, secuencia_id)
    filas = await leer("seg_inscripciones", {"secuencia_id": f"eq.{secuencia_id}", "user_id": f"eq.{user_id}",
                                             "select": "*", "order": "inscrito_en.desc", "limit": "1000"})
    nombres = await _nombres([f["contacto_id"] for f in filas])
    for f in filas:
        c = nombres.get(f["contacto_id"]) or {}
        f["nombre"], f["telefono"] = _nombre(c), c.get("wa_id")
    return {"inscripciones": filas}


@router.post("/secuencias/{secuencia_id}/inscripciones")
async def inscribir(secuencia_id: str, req: InscribirReq, request: Request):
    user_id = await usuario_piloto(request)
    sec = await _secuencia(user_id, secuencia_id)
    pedidos = [i for i in dict.fromkeys(req.contacto_ids or []) if i][:300]
    if not pedidos:
        raise HTTPException(status_code=400, detail="Elige al menos un contacto.")
    contactos = await leer("wa2_contactos", {"id": en_lista(pedidos), "user_id": f"eq.{user_id}",
                                             "select": "id,nombre,wa_id,opt_out,numero_id"})
    previas = await leer("seg_inscripciones", {"contacto_id": en_lista(pedidos),
                                               "select": "id,contacto_id,secuencia_id,estado"})
    ahora = _ahora()
    zona = await zona_de(user_id)
    pasos = sec.get("pasos") or []
    proximo = programar(ahora, int(pasos[0].get("dias") or 0) if pasos else 0,
                        int(sec.get("hora_envio") or 10), zona).isoformat()
    inscritos, omitidos = 0, []
    for c in contactos:
        if c.get("opt_out"):
            omitidos.append({"nombre": _nombre(c), "motivo": "Pidió no recibir mensajes"})
            continue
        if c.get("numero_id") != sec["numero_id"]:
            omitidos.append({"nombre": _nombre(c), "motivo": "Escribió a otro de tus números"})
            continue
        suyas = [p for p in previas if p["contacto_id"] == c["id"]]
        if any(p["estado"] == "activa" for p in suyas):
            omitidos.append({"nombre": _nombre(c), "motivo": "Ya va en una secuencia"})
            continue
        fila = {"estado": "activa", "paso": 0, "intentos": 0, "motivo": None, "proximo_en": proximo,
                "respondio_en": None, "ultimo_envio_en": None, "inscrito_en": ahora.isoformat(), "origen": "manual"}
        misma = next((p for p in suyas if p["secuencia_id"] == secuencia_id), None)
        if misma:
            await actualizar("seg_inscripciones", {"id": f"eq.{misma['id']}"}, fila)
        else:
            await crear("seg_inscripciones", {**fila, "user_id": user_id, "secuencia_id": secuencia_id,
                                              "numero_id": sec["numero_id"], "contacto_id": c["id"]})
        inscritos += 1
    return {"inscritos": inscritos, "omitidos": omitidos}


@router.patch("/inscripciones/{inscripcion_id}")
async def cambiar_inscripcion(inscripcion_id: str, req: InscripcionPatchReq, request: Request):
    user_id = await usuario_piloto(request)
    if req.estado not in ("activa", "pausada", "terminada"):
        raise HTTPException(status_code=400, detail="Estado no válido.")
    cambios: dict = {"estado": req.estado}
    if req.estado == "activa":
        cambios.update({"proximo_en": _ahora().isoformat(), "motivo": None, "intentos": 0})
    elif req.estado == "terminada":
        cambios.update({"proximo_en": None, "motivo": "La quitaste de la secuencia."})
    filas = await actualizar("seg_inscripciones", {"id": f"eq.{inscripcion_id}", "user_id": f"eq.{user_id}"}, cambios)
    if not filas:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada.")
    return {"inscripcion": filas[0]}


@router.get("/contactos")
async def contactos(request: Request, numero_id: str, q: str = "", etiqueta: str = ""):
    user_id = await usuario_piloto(request)
    params = {"user_id": f"eq.{user_id}", "numero_id": f"eq.{numero_id}",
              "select": "id,nombre,wa_id,opt_out,etiquetas", "order": "created_at.desc", "limit": "400"}
    texto = "".join(ch for ch in q if ch.isalnum() or ch in " +-.@").strip()[:40]
    if texto:
        params["or"] = f"(nombre.ilike.*{texto}*,wa_id.ilike.*{texto}*)"
    marca = "".join(ch for ch in etiqueta if ch.isalnum() or ch in " -_").strip()[:40]
    if marca:
        params["etiquetas"] = f'cs.["{marca}"]'
    filas = await leer("wa2_contactos", params)
    ids = [f["id"] for f in filas]
    activos, ultimos = set(), {}
    for i in range(0, len(ids), 150):
        parte = en_lista(ids[i:i + 150])
        activos |= {x["contacto_id"] for x in await leer("seg_inscripciones", {
            "contacto_id": parte, "estado": "eq.activa", "select": "contacto_id"})}
        for c in await leer("wa2_conversaciones", {"contacto_id": parte, "select": "contacto_id,last_inbound_at"}):
            ultimos[c["contacto_id"]] = c.get("last_inbound_at")
    for f in filas:
        f["en_secuencia"] = f["id"] in activos
        f["ultimo_en"] = ultimos.get(f["id"])
    filas.sort(key=lambda f: f.get("ultimo_en") or "", reverse=True)
    return {"contactos": filas}


@router.get("/ajustes")
async def leer_ajustes(request: Request):
    user_id = await usuario_piloto(request)
    return {"ajustes": await ajustes_de(user_id)}


@router.put("/ajustes")
async def guardar_ajustes(req: AjustesReq, request: Request):
    user_id = await usuario_piloto(request)
    datos = limpiar_ajustes(req)
    if datos["numero_id"]:
        await _numero_propio(user_id, datos["numero_id"])
    if datos["eventos_activos"] and not (datos["plantilla_precio"] or datos["plantilla_coincidencia"]):
        raise HTTPException(status_code=400, detail="Elige al menos una plantilla para los avisos.")
    filas = await guardar("seg_ajustes", {**datos, "user_id": user_id, "updated_at": _ahora().isoformat()}, "user_id")
    return {"ajustes": filas[0] if filas else datos}


@router.get("/eventos")
async def eventos(request: Request):
    user_id = await usuario_piloto(request)
    filas = await leer("seg_eventos", {"user_id": f"eq.{user_id}", "select": "*",
                                       "order": "created_at.desc", "limit": "60"})
    nombres = await _nombres([f["contacto_id"] for f in filas])
    for f in filas:
        f["nombre"] = _nombre(nombres.get(f["contacto_id"]))
    return {"eventos": filas}


@router.post("/correr")
async def correr_ahora(request: Request):
    user_id = await usuario_piloto(request)
    return {"resultado": await ciclo_usuario(user_id, forzar_eventos=True)}


@router.on_event("startup")
async def _iniciar_seguimiento() -> None:
    # Manda WhatsApp reales: igual que los recordatorios, solo en UNA instancia.
    if not settings.reminders_enabled:
        log.warning("Seguimiento automático DESACTIVADO por RECORDATORIOS_ACTIVOS.")
        return
    if not usuarios_piloto():
        log.info("Seguimiento automático: sin cuentas en el piloto; el ciclo no arranca.")
        return
    asyncio.create_task(bucle())
