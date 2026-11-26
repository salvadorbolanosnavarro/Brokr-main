"""Motor del Análisis Comparativo de Mercado (ACM).

Todo es matemática fija y transparente: la misma entrada da siempre el mismo
resultado, y cada número se puede explicar al propietario. La IA nunca
calcula aquí; a lo más ayuda antes, a leer anuncios (``core/acm_mercado``).

Conceptos:

* **Sujeto**: la propiedad que el asesor analiza.
* **Comparable**: un inmueble del mercado. Pertenece a un grupo:
  ``activo`` (su competencia), ``vendido`` (cierres reales o anuncios que se
  retiraron) o ``bajas`` (bajó de precio o lleva mucho tiempo publicado).
* **Ajustes**: porcentajes que llevan el precio/m² de cada comparable hacia
  las características del sujeto. Los automáticos son sugerencias; el asesor
  puede cambiarlos, quitarlos o agregar los suyos, y esos se respetan.
* **Rango**: percentiles 25/50/75 del precio/m² ajustado de los comparables
  incluidos, ponderados por similitud, multiplicados por la superficie.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.acm_mercado import entero, normalizar, numero

GRUPOS = ("activo", "vendido", "bajas")
CONSERVACION_PCT = {"excelente": 5.0, "bueno": 0.0, "regular": -7.0, "remodelar": -15.0}
DESCUENTO_DEFECTO = {"venta": 5.0, "renta": 3.0}
DIAS_VENCIDO = 180          # un anuncio activo con más días que esto entra a "bajas"
RADIOS_BUSQUEDA_M = (700, 1500, 3000, 6000)
MIN_COMPARABLES_RADIO = 8
MAX_SELECCION = 24
MAX_INCLUIDOS_INICIAL = 12
SIMILITUD_MIN_INCLUIR = 40.0
SIMILITUD_MIN_CIERRE = 25.0
MAX_CIERRES_EXTRA = 4

# Ajustes automáticos (en % sobre el precio/m² del comparable) y su tope.
ELASTICIDAD_SUPERFICIE = 0.20      # inmuebles más grandes tienen menor precio/m²
PCT_RECAMARA, TOPE_RECAMARAS = 2.5, 7.5
PCT_BANO, TOPE_BANOS = 2.0, 6.0
PCT_ESTACIONAMIENTO, TOPE_ESTACIONAMIENTOS = 3.0, 9.0
PCT_ANIO, TOPE_ANTIGUEDAD = 0.5, 10.0
TOPE_SUPERFICIE = 10.0

CONCEPTOS_AUTO = ("Superficie", "Recámaras", "Baños", "Estacionamientos", "Antigüedad", "Negociación")


# ── Utilidades ──────────────────────────────────────────────────────────────

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _fecha(valor: Any) -> Optional[datetime]:
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day, tzinfo=timezone.utc)
    texto = str(valor).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(texto)
    except ValueError:
        try:
            d = datetime.fromisoformat(texto[:10])
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _dias_entre(a: Any, b: Any) -> Optional[int]:
    da, db = _fecha(a), _fecha(b)
    if not da or not db:
        return None
    return max(0, (db - da).days)


def _tope(valor: float, tope: float) -> float:
    return max(-tope, min(tope, valor))


def distancia_m(lat1: Any, lng1: Any, lat2: Any, lng2: Any) -> Optional[float]:
    """Distancia en metros (haversine). None si falta alguna coordenada."""
    try:
        a1, o1, a2, o2 = (float(x) for x in (lat1, lng1, lat2, lng2))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(x) and x != 0 for x in (a1, o1, a2, o2)):
        return None
    r = 6_371_000.0
    p1, p2 = math.radians(a1), math.radians(a2)
    dp, dl = math.radians(a2 - a1), math.radians(o2 - o1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def caja(lat: float, lng: float, radio_m: float) -> Tuple[float, float, float, float]:
    """(lat_min, lat_max, lng_min, lng_max) que contiene un círculo de radio_m."""
    dlat = radio_m / 111_320.0
    dlng = radio_m / (111_320.0 * max(0.01, math.cos(math.radians(lat))))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


def superficie_base(sujeto_o_comp: Dict[str, Any], tipo: Optional[str] = None) -> Tuple[Optional[float], str]:
    """Superficie con la que se compara: terreno para terrenos, construcción
    para todo lo demás (con terreno como respaldo en casas y bodegas)."""
    tipo = tipo or sujeto_o_comp.get("tipo")
    m2c, m2t = numero(sujeto_o_comp.get("m2_construccion")), numero(sujeto_o_comp.get("m2_terreno"))
    if tipo == "terreno":
        return m2t, "terreno"
    if m2c:
        return m2c, "construccion"
    if tipo in ("casa", "bodega", "otro") and m2t:
        return m2t, "terreno"
    return None, "construccion"


def superficie_en(comp: Dict[str, Any], base: str) -> Optional[float]:
    """Superficie del comparable en la MISMA base que el sujeto: si el sujeto
    se mide por construcción, un comparable que sólo trae terreno no sirve."""
    return numero(comp.get("m2_terreno" if base == "terreno" else "m2_construccion"))


def precio_m2(comp: Dict[str, Any], base: str) -> Optional[float]:
    precio = numero(comp.get("precio_cierre")) or numero(comp.get("precio"))
    sup = superficie_en(comp, base)
    if not precio or not sup:
        return None
    return precio / sup


def redondear(valor: Optional[float], operacion: str) -> Optional[float]:
    if valor is None or not math.isfinite(valor):
        return None
    if operacion == "renta":
        paso = 100 if valor < 100_000 else 1_000
    else:
        paso = 10_000 if valor >= 1_000_000 else 1_000
    return float(int(round(valor / paso)) * paso)


def percentil_ponderado(valores: List[Tuple[float, float]], p: float) -> Optional[float]:
    """Percentil p (0-1) de [(valor, peso)] con interpolación sobre el peso
    acumulado. Con pesos iguales coincide con el percentil clásico."""
    datos = sorted((v, max(w, 1e-9)) for v, w in valores if v is not None and math.isfinite(v))
    if not datos:
        return None
    if len(datos) == 1:
        return datos[0][0]
    total = sum(w for _, w in datos)
    # Posición central de cada punto en la escala acumulada [0, 1].
    acumulado, puntos = 0.0, []
    for v, w in datos:
        puntos.append(((acumulado + w / 2) / total, v))
        acumulado += w
    if p <= puntos[0][0]:
        return puntos[0][1]
    if p >= puntos[-1][0]:
        return puntos[-1][1]
    for (p0, v0), (p1, v1) in zip(puntos, puntos[1:]):
        if p0 <= p <= p1:
            t = 0.0 if p1 == p0 else (p - p0) / (p1 - p0)
            return v0 + t * (v1 - v0)
    return puntos[-1][1]  # pragma: no cover


def _mediana(valores: Iterable[float]) -> Optional[float]:
    v = sorted(x for x in valores if x is not None)
    if not v:
        return None
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2


# ── Grupos, distancia y similitud ───────────────────────────────────────────

def dias_en_mercado(comp: Dict[str, Any], hoy: Optional[datetime] = None) -> Optional[int]:
    hoy = hoy or _ahora()
    if comp.get("origen") == "cierre":
        return _dias_entre(comp.get("publicada_en"), comp.get("fecha_cierre"))
    inicio = comp.get("primera_vez") or comp.get("publicada_en")
    fin = comp.get("retirado_en") if comp.get("estatus") == "retirado" else hoy
    return _dias_entre(inicio, fin)


def grupo_de(comp: Dict[str, Any], hoy: Optional[datetime] = None) -> str:
    if comp.get("origen") == "cierre" or comp.get("estatus") == "retirado":
        return "vendido"
    dias = dias_en_mercado(comp, hoy)
    if (entero(comp.get("bajas_precio")) or 0) > 0 or (dias is not None and dias > DIAS_VENCIDO):
        return "bajas"
    return "activo"


def distancia_comparable(sujeto: Dict[str, Any], comp: Dict[str, Any]) -> Optional[float]:
    d = distancia_m(sujeto.get("lat"), sujeto.get("lng"), comp.get("lat"), comp.get("lng"))
    if d is not None:
        return d
    # Sin coordenadas: misma colonia ≈ 400 m (centro a centro no aplica).
    if normalizar(comp.get("colonia")) and normalizar(comp.get("colonia")) == normalizar(sujeto.get("colonia")):
        return 400.0
    return None


def similitud(sujeto: Dict[str, Any], comp: Dict[str, Any], hoy: Optional[datetime] = None) -> float:
    """Qué tanto se parece un comparable al sujeto, de 0 a 100. Pondera
    distancia (35), superficie (25), recámaras (10), baños (5),
    estacionamientos (5), antigüedad (10) y qué tan reciente es el dato (10).
    Un dato desconocido cuenta como medio parecido, ni bueno ni malo."""
    tipo = sujeto.get("tipo") or "casa"
    puntos = 0.0

    d = comp.get("distancia_m")
    if d is None:
        d = distancia_comparable(sujeto, comp)
    puntos += 35 * (0.35 if d is None else max(0.0, 1 - d / 3000.0))

    s_suj, base = superficie_base(sujeto, tipo)
    s_comp = superficie_en(comp, base)
    if s_suj and s_comp:
        puntos += 25 * max(0.0, 1 - abs(math.log(s_comp / s_suj)) / math.log(1.6))
    else:
        puntos += 25 * 0.3

    def discreto(campo: str, peso: float, escala: Tuple[float, ...]) -> float:
        a, b = numero(sujeto.get(campo)), numero(comp.get(campo))
        if a is None or b is None:
            return peso * 0.5
        dif = int(round(abs(a - b)))
        return peso * (escala[dif] if dif < len(escala) else 0.0)

    if tipo in ("casa", "departamento"):
        puntos += discreto("recamaras", 10, (1.0, 0.6, 0.2))
        puntos += discreto("banos", 5, (1.0, 0.6, 0.2))
    else:
        puntos += 15 * 0.5
    puntos += discreto("estacionamientos", 5, (1.0, 0.7, 0.3))

    a, b = numero(sujeto.get("antiguedad")), numero(comp.get("antiguedad"))
    puntos += 10 * (0.5 if a is None or b is None else max(0.0, 1 - abs(a - b) / 20.0))

    fecha_dato = comp.get("fecha_cierre") or comp.get("ultima_vez") or comp.get("publicada_en")
    edad = _dias_entre(fecha_dato, hoy or _ahora())
    puntos += 10 * (0.5 if edad is None else max(0.0, min(1.0, 1 - (edad - 30) / 240.0)))
    return round(max(0.0, min(100.0, puntos)), 1)


# ── Ajustes ─────────────────────────────────────────────────────────────────

def ajustes_automaticos(sujeto: Dict[str, Any], comp: Dict[str, Any], descuento_pct: float) -> List[Dict[str, Any]]:
    """Ajustes sugeridos para llevar el precio/m² del comparable al sujeto.
    Positivo = el sujeto vale más por m² que el comparable en ese concepto."""
    tipo = sujeto.get("tipo") or "casa"
    salida: List[Dict[str, Any]] = []

    def agrega(concepto: str, pct: float, detalle: str) -> None:
        pct = round(pct, 1)
        if abs(pct) >= 0.1:
            salida.append({"concepto": concepto, "pct": pct, "auto": True, "detalle": detalle})

    s_suj, base = superficie_base(sujeto, tipo)
    s_comp = superficie_en(comp, base)
    if s_suj and s_comp:
        pct = _tope(((s_comp / s_suj) ** ELASTICIDAD_SUPERFICIE - 1) * 100, TOPE_SUPERFICIE)
        agrega("Superficie", pct, f"{s_comp:,.0f} m² vs {s_suj:,.0f} m²")

    def por_unidad(campo: str, concepto: str, pct_u: float, tope: float, solo_residencial: bool) -> None:
        if solo_residencial and tipo not in ("casa", "departamento"):
            return
        a, b = numero(sujeto.get(campo)), numero(comp.get(campo))
        if a is None or b is None or a == b:
            return
        agrega(concepto, _tope((a - b) * pct_u, tope), f"{b:g} vs {a:g}")

    por_unidad("recamaras", "Recámaras", PCT_RECAMARA, TOPE_RECAMARAS, True)
    por_unidad("banos", "Baños", PCT_BANO, TOPE_BANOS, True)
    if tipo != "terreno":
        por_unidad("estacionamientos", "Estacionamientos", PCT_ESTACIONAMIENTO, TOPE_ESTACIONAMIENTOS, False)
        a, b = numero(sujeto.get("antiguedad")), numero(comp.get("antiguedad"))
        if a is not None and b is not None and a != b:
            agrega("Antigüedad", _tope((b - a) * PCT_ANIO, TOPE_ANTIGUEDAD), f"{b:g} vs {a:g} años")

    # Los precios publicados son de oferta; los cierres ya son precio real.
    if comp.get("origen") != "cierre" and descuento_pct:
        agrega("Negociación", -abs(descuento_pct), "Precio de oferta → precio de cierre estimado")
    return salida


def combinar_ajustes(automaticos: List[Dict[str, Any]], actuales: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Los ajustes que el asesor tocó (auto=False) mandan: reemplazan al
    automático del mismo concepto. Un concepto automático que el asesor
    eliminó queda registrado como pct=0 manual, así no vuelve a aparecer."""
    manuales = [dict(a) for a in (actuales or []) if not a.get("auto")]
    tocados = {normalizar(a.get("concepto")) for a in manuales}
    salida = [a for a in automaticos if normalizar(a.get("concepto")) not in tocados]
    for a in manuales:
        try:
            a["pct"] = round(float(a.get("pct") or 0), 1)
        except (TypeError, ValueError):
            a["pct"] = 0.0
        a["pct"] = _tope(a["pct"], 50.0)
        a["concepto"] = str(a.get("concepto") or "Ajuste")[:60]
        a["auto"] = False
        salida.append(a)
    return salida


def total_ajustes(ajustes: Iterable[Dict[str, Any]]) -> float:
    total = 0.0
    for a in ajustes:
        try:
            total += float(a.get("pct") or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 1)


# ── Calibración con cierres reales ──────────────────────────────────────────

def calibrar_descuento(cierres: Iterable[Dict[str, Any]], operacion: str) -> Dict[str, Any]:
    """Diferencia mediana entre precio publicado y precio de cierre en los
    cierres de la cuenta. Con menos de 5 cierres útiles se usa el valor por
    defecto (5% venta, 3% renta)."""
    pcts = []
    for c in cierres:
        op = "renta" if str(c.get("tipo_operacion") or c.get("operacion") or "venta").startswith("renta") else "venta"
        if op != operacion:
            continue
        pub, cie = numero(c.get("precio_publicacion")), numero(c.get("precio_cierre"))
        if not pub or not cie:
            continue
        pct = (pub - cie) / pub * 100
        if -5 <= pct <= 30:
            pcts.append(pct)
    defecto = DESCUENTO_DEFECTO.get(operacion, 5.0)
    if len(pcts) < 5:
        return {"pct": defecto, "fuente": "defecto", "n": len(pcts)}
    return {"pct": round(max(0.0, _mediana(pcts) or defecto), 1), "fuente": "cierres", "n": len(pcts)}


# ── Selección y cálculo ─────────────────────────────────────────────────────

def compatible(sujeto: Dict[str, Any], comp: Dict[str, Any]) -> bool:
    if comp.get("operacion") != sujeto.get("operacion"):
        return False
    if comp.get("tipo") != sujeto.get("tipo"):
        return False
    _, base = superficie_base(sujeto)
    return precio_m2(comp, base) is not None


def preparar_comparable(sujeto: Dict[str, Any], comp: Dict[str, Any], descuento_pct: float,
                        hoy: Optional[datetime] = None) -> Dict[str, Any]:
    """Calcula los campos derivados de un comparable sin cambiar las decisiones
    del asesor (incluido, ajustes manuales, nota)."""
    c = dict(comp)
    _, base = superficie_base(sujeto)
    d = distancia_comparable(sujeto, c)
    if d is not None:
        c["distancia_m"] = round(d)
    c["grupo"] = c.get("grupo") if c.get("origen") == "manual" and c.get("grupo") in GRUPOS else grupo_de(c, hoy)
    c["dias_mercado"] = c.get("dias_mercado") if c.get("origen") == "manual" else dias_en_mercado(c, hoy)
    c["superficie"], c["base_superficie"] = superficie_en(c, base), base
    pm2 = precio_m2(c, base)
    c["precio_m2"] = round(pm2, 2) if pm2 else None
    c["similitud"] = similitud(sujeto, c, hoy)
    misma_moneda = (c.get("moneda") or "MXN") == (sujeto.get("moneda") or "MXN")
    c["ajustes"] = combinar_ajustes(ajustes_automaticos(sujeto, c, descuento_pct), c.get("ajustes"))
    c["ajuste_total_pct"] = total_ajustes(c["ajustes"])
    c["precio_m2_ajustado"] = round(pm2 * (1 + c["ajuste_total_pct"] / 100), 2) if pm2 and misma_moneda else None
    if not misma_moneda:
        c["incluido"] = False
        c["motivo"] = f"Publicado en {c.get('moneda')}"
    return c


def marcar_atipicos(comps: List[Dict[str, Any]]) -> None:
    """Marca precios/m² muy alejados del resto (desviación robusta > 3.5)."""
    valores = [c["precio_m2_ajustado"] for c in comps if c.get("incluido") and c.get("precio_m2_ajustado")]
    for c in comps:
        c["atipico"] = False
    if len(valores) < 4:
        return
    med = _mediana(valores)
    mad = _mediana(abs(v - med) for v in valores)
    if not mad:
        return
    for c in comps:
        v = c.get("precio_m2_ajustado")
        if v and abs(0.6745 * (v - med) / mad) > 3.5:
            c["atipico"] = True


def seleccionar(sujeto: Dict[str, Any], candidatos: Iterable[Dict[str, Any]], descuento_pct: float,
                hoy: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Primera propuesta de comparables: compatibles, ordenados por similitud,
    con los mejores ya incluidos y los atípicos fuera (el asesor decide al
    final). Garantiza que los vendidos reales entren aunque estén más lejos."""
    vistos, preparados = set(), []
    for comp in candidatos:
        if not compatible(sujeto, comp):
            continue
        clave = comp.get("id") or comp.get("huella") or comp.get("url")
        if clave in vistos:
            continue
        vistos.add(clave)
        c = preparar_comparable(sujeto, {**comp, "ajustes": []}, descuento_pct, hoy)
        s_suj, _ = superficie_base(sujeto)
        if s_suj and c.get("superficie") and not (0.5 <= c["superficie"] / s_suj <= 2.0):
            continue
        preparados.append(c)
    preparados.sort(key=lambda c: (-c["similitud"], c.get("distancia_m") or 9e9))
    # Los cierres reales son el dato más valioso (precio pagado, no pedido):
    # siempre entran a la lista y, si se parecen razonablemente, incluidos.
    cierres = [c for c in preparados if c.get("origen") == "cierre" and c["similitud"] >= SIMILITUD_MIN_CIERRE][:MAX_CIERRES_EXTRA]
    resto = [c for c in preparados if c not in cierres]
    elegidos = resto[:MAX_SELECCION - len(cierres)]
    for i, c in enumerate(elegidos):
        c["incluido"] = bool(c.get("precio_m2_ajustado")) and i < MAX_INCLUIDOS_INICIAL and c["similitud"] >= SIMILITUD_MIN_INCLUIR
    for c in cierres:
        c["incluido"] = bool(c.get("precio_m2_ajustado"))
    elegidos = sorted(elegidos + cierres, key=lambda c: -c["similitud"])
    marcar_atipicos(elegidos)
    for c in elegidos:
        if c["atipico"] and c["incluido"]:
            c["incluido"] = False
            c["motivo"] = "Precio/m² muy alejado del resto"
    marcar_atipicos(elegidos)
    return elegidos


def _confianza(n: int, dispersion: Optional[float], sim_media: Optional[float]) -> Tuple[str, str]:
    if n == 0:
        return "sin_datos", "No hay comparables incluidos todavía."
    disp = dispersion if dispersion is not None else 1.0
    if n >= 6 and disp <= 0.25 and (sim_media or 0) >= 55:
        return "alta", f"{n} comparables parecidos y con precios consistentes entre sí."
    if n >= 3 and disp <= 0.45:
        return "media", f"{n} comparables; los precios por m² varían {disp * 100:.0f}% entre el cuarto más bajo y el más alto."
    if n < 3:
        return "baja", f"Sólo {n} comparable{'s' if n != 1 else ''} incluido{'s' if n != 1 else ''}: conviene sumar más."
    return "baja", f"Los precios por m² de los comparables varían mucho ({disp * 100:.0f}%): revisa cuáles son de verdad parecidos."


def _dias_por_banda(comps: List[Dict[str, Any]], p25: float, p75: float) -> Dict[str, Optional[int]]:
    bandas: Dict[str, List[int]] = {"rapido": [], "mercado": [], "aspiracional": []}
    for c in comps:
        v, dias = c.get("precio_m2_ajustado"), c.get("dias_mercado")
        if not v or dias is None or c.get("grupo") == "activo":
            continue  # sólo inmuebles que ya salieron del mercado o llevan tiempo
        banda = "rapido" if v <= p25 else ("aspiracional" if v >= p75 else "mercado")
        bandas[banda].append(dias)
    return {k: (int(_mediana(v)) if len(v) >= 2 else None) for k, v in bandas.items()}


def resumen_mercado(comps: List[Dict[str, Any]]) -> Dict[str, Any]:
    por_grupo = {g: [c for c in comps if c.get("grupo") == g] for g in GRUPOS}
    activos = por_grupo["activo"] + por_grupo["bajas"]
    con_bajas = [c for c in activos if (entero(c.get("bajas_precio")) or 0) > 0]
    pm2 = lambda lista: _mediana(c["precio_m2"] for c in lista if c.get("precio_m2"))  # noqa: E731
    return {
        "en_venta": len(activos),
        "vendidos": len(por_grupo["vendido"]),
        "con_bajas_o_vencidos": len(por_grupo["bajas"]),
        "pct_con_bajas": round(len(con_bajas) / len(activos) * 100) if activos else None,
        "dias_mercado_mediana": _mediana(c["dias_mercado"] for c in activos if c.get("dias_mercado") is not None),
        "dias_venta_mediana": _mediana(c["dias_mercado"] for c in por_grupo["vendido"] if c.get("dias_mercado") is not None),
        "precio_m2_oferta_mediana": round(pm2(activos), 0) if pm2(activos) else None,
        "precio_m2_vendidos_mediana": round(pm2(por_grupo["vendido"]), 0) if pm2(por_grupo["vendido"]) else None,
    }


def calcular(sujeto: Dict[str, Any], comparables: List[Dict[str, Any]], descuento: Optional[Dict[str, Any]] = None,
             hoy: Optional[datetime] = None) -> Dict[str, Any]:
    """Recalcula todo el análisis a partir de las decisiones del asesor.
    Devuelve los comparables ya preparados y el resultado."""
    operacion = sujeto.get("operacion") or "venta"
    descuento = descuento or {"pct": DESCUENTO_DEFECTO.get(operacion, 5.0), "fuente": "defecto", "n": 0}
    comps = [preparar_comparable(sujeto, c, float(descuento.get("pct") or 0), hoy) for c in comparables]
    marcar_atipicos(comps)

    incluidos = [c for c in comps if c.get("incluido") and c.get("precio_m2_ajustado")]
    pares = [(c["precio_m2_ajustado"], max(c["similitud"], 5.0)) for c in incluidos]
    p25 = percentil_ponderado(pares, 0.25)
    p50 = percentil_ponderado(pares, 0.50)
    p75 = percentil_ponderado(pares, 0.75)
    sup, base = superficie_base(sujeto, sujeto.get("tipo"))
    general = CONSERVACION_PCT.get(sujeto.get("conservacion") or "bueno", 0.0)
    try:
        general += float(sujeto.get("ajuste_general_pct") or 0)
    except (TypeError, ValueError):
        pass
    factor = 1 + general / 100

    def valor(pm2: Optional[float]) -> Optional[float]:
        return redondear(pm2 * sup * factor, operacion) if pm2 and sup else None

    dispersion = round((p75 - p25) / p50, 3) if p25 and p50 and p75 else None
    sim_media = round(sum(c["similitud"] for c in incluidos) / len(incluidos), 1) if incluidos else None
    nivel, razon = _confianza(len(incluidos), dispersion, sim_media)
    dias = _dias_por_banda(comps, p25, p75) if p25 and p75 else {"rapido": None, "mercado": None, "aspiracional": None}

    resultado = {
        "moneda": sujeto.get("moneda") or "MXN",
        "operacion": operacion,
        "superficie": sup,
        "base_superficie": base,
        "ajuste_general_pct": round(general, 1),
        "descuento": descuento,
        "n_comparables": len(comps),
        "n_incluidos": len(incluidos),
        "precio_m2": {
            "min": round(min(v for v, _ in pares), 0) if pares else None,
            "p25": round(p25, 0) if p25 else None,
            "mediana": round(p50, 0) if p50 else None,
            "p75": round(p75, 0) if p75 else None,
            "max": round(max(v for v, _ in pares), 0) if pares else None,
        },
        "valor": {"bajo": valor(p25), "medio": valor(p50), "alto": valor(p75)},
        "dispersion": dispersion,
        "similitud_media": sim_media,
        "confianza": nivel,
        "razon_confianza": razon,
        "estrategia_sugerida": {
            "rapido": {"precio": valor(p25), "dias_estimados": dias["rapido"]},
            "mercado": {"precio": valor(p50), "dias_estimados": dias["mercado"]},
            "aspiracional": {"precio": valor(p75), "dias_estimados": dias["aspiracional"]},
        },
        "mercado": resumen_mercado(comps),
        "calculado_en": (hoy or _ahora()).isoformat(),
    }
    return {"comparables": comps, "resultado": resultado}


def comparar_versiones(anterior: Dict[str, Any], nuevo: Dict[str, Any]) -> Dict[str, Any]:
    """Qué cambió entre dos cálculos de un mismo ACM (para 'Actualizar ACM')."""
    def v(r: Dict[str, Any], k: str) -> Optional[float]:
        return numero((r.get("valor") or {}).get(k))

    ra, rn = anterior.get("resultado") or {}, nuevo.get("resultado") or {}
    cambio = None
    if v(ra, "medio") and v(rn, "medio"):
        cambio = round((v(rn, "medio") - v(ra, "medio")) / v(ra, "medio") * 100, 1)
    ids_a = {c.get("id") for c in anterior.get("comparables") or []}
    ids_n = {c.get("id") for c in nuevo.get("comparables") or []}
    vendidos_ahora = [
        c for c in nuevo.get("comparables") or []
        if c.get("grupo") == "vendido" and c.get("id") in ids_a
        and next((x for x in anterior.get("comparables") or [] if x.get("id") == c.get("id")), {}).get("grupo") != "vendido"
    ]
    return {
        "valor_medio_antes": v(ra, "medio"),
        "valor_medio_ahora": v(rn, "medio"),
        "cambio_pct": cambio,
        "comparables_nuevos": len(ids_n - ids_a),
        "comparables_que_salieron": len(ids_a - ids_n),
        "se_vendieron_o_retiraron": len(vendidos_ahora),
        "mercado_antes": ra.get("mercado"),
        "mercado_ahora": rn.get("mercado"),
    }
