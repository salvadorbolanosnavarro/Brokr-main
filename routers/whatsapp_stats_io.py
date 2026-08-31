from __future__ import annotations


async def sb_diag_core(table: str, params: dict, *, get_rows, httpx) -> tuple[list, str]:
    """Diagnostic read: unlike sb_get, keep the database error text visible."""
    try:
        data = await get_rows(table, params, timeout=25)
        return data, ""
    except httpx.HTTPStatusError as exc:
        r = exc.response
        return [], f"{r.status_code}: {r.text[:200]}"
    except Exception as e:
        return [], str(e)[:200]


async def sb_get_paginado_core(table: str, params: dict, tope: int = 40000,
                               paralelo: int = 6, *, _sb_diag, asyncio) -> tuple[list, str]:
    """PostgREST corta en 1000 filas. Para estadísticas necesitamos el historial
    completo, así que se pagina — pero EN PARALELO. En serie, un historial de
    30 mil mensajes son 30 viajes de ida y vuelta y Railway corta la conexión
    antes de terminar (el navegador lo ve como 'Failed to fetch').
    Devuelve (filas, error)."""
    salida: list = []
    error = ""
    pagina = 1000
    bloque = 0
    while len(salida) < tope and bloque < 40:
        tareas = []
        for k in range(paralelo):
            p = dict(params)
            p["limit"] = str(pagina)
            p["offset"] = str((bloque * paralelo + k) * pagina)
            tareas.append(_sb_diag(table, p))
        resultados = await asyncio.gather(*tareas, return_exceptions=True)
        traidas = 0
        for res in resultados:
            if isinstance(res, Exception):
                error = error or str(res)[:200]
                continue
            filas, err = res
            if err:
                error = error or err
                continue
            salida.extend(filas)
            traidas += len(filas)
        if error and not salida:
            break
        if traidas < pagina * paralelo:
            break
        bloque += 1
    return salida[:tope], error
