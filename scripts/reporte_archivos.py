#!/usr/bin/env python3
"""Reporte de archivos riesgosos en Supabase Storage. SOLO LECTURA.

Lógica en core/reporte_archivos.py (la misma que usa el botón de la consola de
administrador). No abre, copia ni borra archivos. En pantalla solo imprime
totales; el CSV (cuenta, bucket, ruta, motivo) es privado.

    python scripts/reporte_archivos.py [--salida reporte.csv] [--sin-sensibles]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.reporte_archivos import a_csv, construir  # noqa: E402


async def _correr(salida: Path, incluir_sensibles: bool) -> int:
    print("Reporte de archivos (solo lectura: no abre, copia ni borra nada)")
    filas, resumen = await construir(incluir_sensibles)
    salida.write_text(a_csv(filas), encoding="utf-8")
    print(f"  archivos revisados: {sum(resumen['revisados'].values())}")
    for bucket, n in sorted(resumen["revisados"].items()):
        estado = "público" if resumen["buckets"].get(bucket) else "privado"
        print(f"    {bucket} ({estado}): {n}")
    print(f"  hallazgos: {resumen['hallazgos']}")
    for motivo, n in resumen["por_motivo"].items():
        print(f"    {n:6d}  {motivo}")
    print(f"  reporte detallado: {salida}  (privado: puede traer nombres de archivo de clientes)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reporte de archivos riesgosos (solo lectura)")
    ap.add_argument("--salida", default="reporte-archivos.csv")
    ap.add_argument("--sin-sensibles", action="store_true",
                    help="no listar cada archivo de cliente en bucket público")
    args = ap.parse_args(argv)
    try:
        return asyncio.run(_correr(Path(args.salida), not args.sin_sensibles))
    except RuntimeError as exc:
        print(f"ERROR de configuración: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
