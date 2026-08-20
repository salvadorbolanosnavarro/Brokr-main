"""Pure timezone/calendar helpers for WhatsApp 2.0."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hora_local(zona: str | None = None) -> datetime:
    try:
        return datetime.now(ZoneInfo(zona or "America/Mexico_City"))
    except Exception:
        return datetime.now(timezone.utc) + timedelta(hours=-6)


def fmt_fecha_larga(dt: datetime) -> str:
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month-1]} de {dt.year}, {dt.strftime('%H:%M')}"


def fecha_hora_utc_iso(fecha: str, hora: str, zona: str | None = None) -> str | None:
    zona = zona or "America/Mexico_City"
    try:
        y, m, d = (int(x) for x in fecha.split("-"))
        hh, mi = (int(x) for x in hora.split(":")[:2])
    except Exception:
        return None
    try:
        local_dt = datetime(y, m, d, hh, mi, tzinfo=ZoneInfo(zona))
    except Exception:
        local_dt = datetime(y, m, d, hh, mi, tzinfo=ZoneInfo("America/Mexico_City"))
    return local_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def construir_ics(fecha: str, hora: str, titulo: str, descripcion: str, zona: str | None = None) -> str:
    zona = zona or "America/Mexico_City"
    try:
        y, m, d = (int(x) for x in fecha.split("-"))
        hh, mi = (int(x) for x in hora.split(":")[:2])
    except Exception:
        ahora = hora_local(zona)
        y, m, d, hh, mi = ahora.year, ahora.month, ahora.day, ahora.hour, ahora.minute
    try:
        local_dt = datetime(y, m, d, hh, mi, tzinfo=ZoneInfo(zona))
    except Exception:
        local_dt = datetime(y, m, d, hh, mi, tzinfo=ZoneInfo("America/Mexico_City"))
    inicio = local_dt.astimezone(timezone.utc)
    fin = inicio + timedelta(hours=1)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = f"{stamp}-{y}{m}{d}{hh}{mi}@broquer.app"
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Broquer//WhatsApp2//ES",
        "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
        f"DTSTART:{inicio.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTEND:{fin.strftime('%Y%m%dT%H%M%SZ')}",
        f"SUMMARY:{titulo}", f"DESCRIPTION:{descripcion}",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(lines)
