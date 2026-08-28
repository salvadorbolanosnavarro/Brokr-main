"""Canonical property search for WhatsApp 2.0."""
from __future__ import annotations

from routers.whatsapp_data import sb_get


async def _buscar_inmuebles(user_id: str, filtros: dict, limit: int = 3) -> tuple[list, bool]:
    """Devuelve (propiedades, zona_sin_resultados). zona_sin_resultados es True
    cuando el prospecto pidió una zona concreta y de verdad no hay nada ahí —
    para que el mensaje sea honesto en vez de mandar propiedades de otro lado
    como si fueran lo que se pidió.

    IMPORTANTE sobre precisión: 'ciudad' es un filtro DURO — si el prospecto
    dijo Morelia, jamás se relaja para buscar en otros municipios. 'colonia'
    se intenta primero exacta y, si no hay nada, con el nombre del desarrollo/
    fraccionamiento más amplio (zona_amplia) — pero SIEMPRE dentro de la misma
    ciudad. Nunca se hace un OR suelto de palabras sin relación entre sí: eso
    era lo que antes hacía que 'Morelia' por sí solo trajera cualquier cosa de
    la ciudad, o que una palabra como 'Olivar' apareciera de casualidad en la
    calle de un inmueble de otro municipio.
    """
    sel = ("id,titulo,tipo,operacion,precio,moneda,colonia,ciudad,calle,"
           "num_exterior,recamaras,banos,m2_construccion,fotos,estatus,descripcion")
    # OJO con el estatus: antes esto era `estatus=not.in.(...)` a secas, y en
    # Postgres una comparación contra NULL nunca da verdadero. Es decir, TODA
    # propiedad con el estatus vacío quedaba invisible para la IA — y muchas
    # propiedades importadas o capturadas rápido no traen estatus. El agente
    # tenía inventario y la IA le decía al prospecto que no había nada.
    #
    # 'no_activa' es el estatus de los inmuebles que la propia IA dio de alta
    # con lo que le mandó un tercero por WhatsApp. Esos NUNCA se le ofrecen a
    # un comprador: nadie ha verificado el precio, la titularidad ni que la
    # propiedad exista. Solo salen del cajón cuando el asesor los activa.
    base = {"user_id": f"eq.{user_id}", "select": sel,
            "or": "(estatus.is.null,estatus.not.in.(vendida,rentada,suspendida,no_activa))",
            "order": "updated_at.desc", "limit": str(limit)}
    op = (filtros.get("operacion") or "").strip().lower()
    if op in ("venta", "renta"):
        base["operacion"] = f"eq.{op}"
    tipo = (filtros.get("tipo") or "").strip()
    if tipo:
        base["tipo"] = f"ilike.*{tipo}*"

    ciudad = (filtros.get("ciudad") or "").strip()
    colonia = (filtros.get("colonia") or "").strip()
    zona_amplia = (filtros.get("zona_amplia") or "").strip()

    def _con_precio_recamaras(p: dict) -> dict:
        p = dict(p)
        if filtros.get("precio_max"):
            try:
                p["precio"] = f"lte.{int(filtros['precio_max'])}"
            except Exception:
                pass
        if filtros.get("recamaras"):
            try:
                p["recamaras"] = f"gte.{int(filtros['recamaras'])}"
            except Exception:
                pass
        return p

    if ciudad or colonia or zona_amplia:
        # La ciudad, si se pidió, es OBLIGATORIA en las tres pasadas — nunca
        # se quita, así jamás se ofrece algo de un municipio distinto.
        def _con_ciudad(p: dict) -> dict:
            if ciudad:
                p = dict(p)
                p["ciudad"] = f"ilike.*{ciudad}*"
            return p

        intentos = []
        if colonia:
            intentos.append({"colonia": f"ilike.*{colonia}*"})
        if zona_amplia and zona_amplia.lower() != colonia.lower():
            intentos.append({"colonia": f"ilike.*{zona_amplia}*"})
        if colonia:
            # Por si el nombre del desarrollo está capturado en la calle y no
            # en la colonia (pasa seguido con fraccionamientos nuevos).
            intentos.append({"calle": f"ilike.*{colonia}*"})
        if not intentos and ciudad:
            intentos.append({})  # solo ciudad, sin colonia — caso "casas en Morelia"

        for extra in intentos:
            params = _con_ciudad({**base, **extra})
            rows = await sb_get("propiedades", _con_precio_recamaras(params))
            if rows:
                return rows, False

        # De verdad no hay nada en esa zona/ciudad: se avisa, no se manda otra
        # cosa en su lugar disfrazada de lo que se pidió.
        return [], True

    # Sin zona pedida: aquí sí tiene sentido relajar precio/recámaras si son
    # demasiado estrictos, porque no cambian LO QUE ES la propiedad, solo el
    # rango — y de perdida se le enseña algo parecido a lo que busca.
    rows = await sb_get("propiedades", _con_precio_recamaras(base))
    if not rows and (filtros.get("precio_max") or filtros.get("recamaras")):
        rows = await sb_get("propiedades", base)
    return rows or [], False
