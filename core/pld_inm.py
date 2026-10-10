"""Aviso de Actividad Vulnerable · Fracción V (Inmuebles, clave INM).

Arma el XML exactamente como lo pide el esquema oficial de la UIF
(``core/pld/inm.xsd``, descargado de pld.hacienda.gob.mx) y lo VALIDA contra
ese mismo esquema antes de entregarlo. Los catálogos (``catalogos_inm.json``)
se extrajeron de la plantilla oficial del SPPLD (Inmuebles_v4_5.xlsm).

Dos niveles de revisión:
  1. ``problemas``: lo que el SAT rechazaría y el agente puede corregir
     (dato faltante, clave fuera de catálogo). Se reportan en español, por
     operación, antes de armar nada.
  2. ``validar_xsd``: el XML final contra el XSD oficial. Si esto falla es un
     bug de Broquer, no del agente; nunca se entrega un archivo inválido.

Sin estado, sin HTTP, sin base de datos: todo entra por parámetros.
"""
from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

NS = "http://www.uif.shcp.gob.mx/recepcion/inm"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
XSD_PATH = Path(__file__).parent / "pld" / "inm.xsd"
CATALOGOS_PATH = Path(__file__).parent / "pld" / "catalogos_inm.json"

# La única clave válida para fracción V: "COMPRA VENTA" (regla VC3712R1).
TIPO_OPERACION_INM = "501"
FIGURA_INTERMEDIARIO = "3"
ALERTA_SIN_ALERTA = "100"
ALERTA_OTRA = "9999"

# Tipos de operación de Broquer que sí son fracción V. El arrendamiento es
# otra actividad (ARI, fracción XV) y no puede ir en este archivo.
TIPOS_BROQUER_INM = {"compraventa", "promesa", "aportacion"}

_MONEDA_ISO = {"MXN": "1", "USD": "2", "EUR": "3"}


@lru_cache(maxsize=1)
def catalogos() -> Dict[str, List[List[str]]]:
    datos = json.loads(CATALOGOS_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in datos.items() if not k.startswith("_")}


def _claves(nombre: str) -> set:
    return {c for c, _ in catalogos().get(nombre, [])}


# ── Normalización de texto (el SPPLD solo acepta MAYÚSCULAS sin acentos) ──

def _plano(v) -> str:
    s = "" if v is None else str(v).strip().upper()
    s = s.replace("Ñ", "\x00")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s.replace("\x00", "Ñ")


def _limpia(v, permitidos: str, maximo: int) -> str:
    s = re.sub(f"[^{permitidos}]", " ", _plano(v))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:maximo].strip()


_NOMBRE = "A-ZÑ "
_DENOMINACION = r"A-ZÑ0-9 #\-\.&,_@'"
_DIRECCION = r"A-ZÑ0-9 ,\.:/\-"
_DESCRIPCION = r"A-ZÑ0-9 ,\.:/'\$\-"
_FOLIO = r"A-Z0-9_\-"


def _nombre(v) -> str:
    return _limpia(v, _NOMBRE, 200)


def _apellido(v) -> str:
    # Sin apellido se capturan cuatro equis (VC35112R1 / VC35113R1).
    return _nombre(v) or "XXXX"


def _fecha(v) -> str:
    s = re.sub(r"\D", "", str(v or ""))[:8]
    return s if len(s) == 8 else ""


def _monto(v, enteros: int = 14) -> str:
    try:
        d = Decimal(str(v)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return ""
    if d < 0:
        return ""
    s = f"{d:.2f}"
    return s if len(s.split(".")[0]) <= enteros else ""


def _rfc(v, moral: bool) -> str:
    s = re.sub(r"[^A-ZÑ&0-9]", "", _plano(v))
    patron = r"[A-ZÑ&]{3}\d{6}[A-Z0-9]{3}" if moral else r"[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}"
    return s if re.fullmatch(patron, s) else ""


def _curp(v) -> str:
    s = re.sub(r"[^A-Z0-9]", "", _plano(v))
    return s if re.fullmatch(r"[A-Z]{4}\d{6}[MH][A-Z]{5}[A-Z0-9]{2}", s) else ""


def _pais(v) -> str:
    s = _plano(v)
    if s in _claves("pais"):
        return s
    if s.startswith("MEX") or s in ("", "MX"):
        return "MX" if s else ""
    for clave, nombre in catalogos()["pais"]:
        if _plano(nombre) == s:
            return clave
    return ""


def _cp(v) -> str:
    s = re.sub(r"\D", "", str(v or ""))
    return s if len(s) == 5 else ""


def _referencia(v) -> str:
    return re.sub(r"[^A-Z0-9]", "", _plano(v))[:14]


def _nodo(padre, etiqueta: str, valor: Optional[str] = None):
    e = ET.SubElement(padre, f"{{{NS}}}{etiqueta}")
    if valor is not None:
        e.text = valor
    return e


def _opcional(padre, etiqueta: str, valor: str) -> None:
    if valor:
        _nodo(padre, etiqueta, valor)


def nombre_de(exp: dict) -> str:
    if (exp.get("tipo_persona") or "fisica") == "fisica":
        return " ".join(x for x in (exp.get("nombre"), exp.get("apellido_paterno"),
                                    exp.get("apellido_materno")) if x) or "Cliente"
    return exp.get("razon_social") or "Cliente"


# ── Personas ──────────────────────────────────────────────────────────────

def _persona_aviso(padre, exp: dict, faltan: List[str]) -> None:
    """<tipo_persona> completo (persona objeto del aviso)."""
    tipo = (exp.get("tipo_persona") or "fisica").lower()
    tp = _nodo(padre, "tipo_persona")
    if tipo == "fisica":
        pf = _nodo(tp, "persona_fisica")
        nombre = _nombre(exp.get("nombre"))
        if not nombre:
            faltan.append("nombre del cliente")
        _nodo(pf, "nombre", nombre or "XXXX")
        _nodo(pf, "apellido_paterno", _apellido(exp.get("apellido_paterno")))
        _nodo(pf, "apellido_materno", _apellido(exp.get("apellido_materno")))
        fn, rfc, curp = _fecha(exp.get("fecha_nacimiento")), _rfc(exp.get("rfc"), False), _curp(exp.get("curp"))
        if not (fn or rfc or curp):
            faltan.append("fecha de nacimiento, RFC con homoclave o CURP del cliente (al menos uno)")
        _opcional(pf, "fecha_nacimiento", fn)
        _opcional(pf, "rfc", rfc)
        _opcional(pf, "curp", curp)
        pais = _pais(exp.get("nacionalidad"))
        if not pais:
            faltan.append("nacionalidad del cliente (elige el país del catálogo)")
        _nodo(pf, "pais_nacionalidad", pais or "MX")
        act = str(exp.get("actividad_economica") or "").strip()
        if act not in _claves("actividad_economica"):
            faltan.append("actividad económica del cliente (elige una del catálogo de la UIF)")
            act = "1000000"
        _nodo(pf, "actividad_economica", act)
        return

    moral = tipo == "moral"
    pm = _nodo(tp, "persona_moral" if moral else "fideicomiso")
    razon = _limpia(exp.get("razon_social"), _DENOMINACION, 254)
    if not razon:
        faltan.append("razón social" if moral else "denominación del fiduciario")
    _nodo(pm, "denominacion_razon", razon or "XXXX")
    rfc = _rfc(exp.get("rfc_moral"), True)
    if moral:
        fc = _fecha(exp.get("fecha_constitucion"))
        if not (fc or rfc):
            faltan.append("fecha de constitución o RFC de la empresa")
        _opcional(pm, "fecha_constitucion", fc)
        _opcional(pm, "rfc", rfc)
        # La pantalla no pide nacionalidad a las empresas: sin dato, una
        # sociedad constituida en México (el caso normal) va como MX.
        _nodo(pm, "pais_nacionalidad", _pais(exp.get("nacionalidad")) or "MX")
        giro = str(exp.get("giro_mercantil") or "").strip()
        if giro not in _claves("giro_mercantil"):
            faltan.append("giro mercantil de la empresa (elige uno del catálogo de la UIF)")
            giro = "1000000"
        _nodo(pm, "giro_mercantil", giro)
        rep = _nodo(pm, "representante_apoderado")
    else:
        ident = _limpia(exp.get("folio_mercantil"), _DENOMINACION, 40)
        if not (rfc or ident):
            faltan.append("RFC o número del fideicomiso")
        _opcional(pm, "rfc", rfc)
        _opcional(pm, "identificador_fideicomiso", ident)
        rep = _nodo(pm, "apoderado_delegado")

    rnombre = _nombre(exp.get("rep_nombre"))
    if not rnombre:
        faltan.append("nombre del representante legal")
    _nodo(rep, "nombre", rnombre or "XXXX")
    _nodo(rep, "apellido_paterno", _apellido(exp.get("rep_apellido_paterno")))
    _nodo(rep, "apellido_materno", _apellido(exp.get("rep_apellido_materno")))
    rrfc, rcurp = _rfc(exp.get("rep_rfc"), False), _curp(exp.get("rep_curp"))
    if not (rrfc or rcurp):
        faltan.append("RFC con homoclave o CURP del representante legal")
    _opcional(rep, "rfc", rrfc)
    _opcional(rep, "curp", rcurp)


def _persona_simple(padre, d: dict, faltan: List[str], quien: str) -> None:
    """<tipo_persona> simple (dueño beneficiario y contraparte)."""
    tp = _nodo(padre, "tipo_persona")
    tipo = (d.get("tipo_persona") or "fisica").lower()
    if tipo == "fisica":
        pf = _nodo(tp, "persona_fisica")
        nombre = _nombre(d.get("nombre"))
        if not nombre:
            faltan.append(f"nombre de {quien}")
        _nodo(pf, "nombre", nombre or "XXXX")
        _nodo(pf, "apellido_paterno", _apellido(d.get("apellido_paterno")))
        _nodo(pf, "apellido_materno", _apellido(d.get("apellido_materno")))
        _opcional(pf, "fecha_nacimiento", _fecha(d.get("fecha_nacimiento")))
        _opcional(pf, "rfc", _rfc(d.get("rfc"), False))
        _opcional(pf, "curp", _curp(d.get("curp")))
        _opcional(pf, "pais_nacionalidad", _pais(d.get("nacionalidad")))
        return
    pm = _nodo(tp, "persona_moral" if tipo == "moral" else "fideicomiso")
    razon = _limpia(d.get("razon_social"), _DENOMINACION, 254)
    if not razon:
        faltan.append(f"razón social de {quien}")
    _nodo(pm, "denominacion_razon", razon or "XXXX")
    if tipo == "moral":
        _opcional(pm, "fecha_constitucion", _fecha(d.get("fecha_constitucion")))
    _opcional(pm, "rfc", _rfc(d.get("rfc_moral") or d.get("rfc"), True))
    if tipo == "moral":
        _opcional(pm, "pais_nacionalidad", _pais(d.get("nacionalidad")))


def _domicilio(padre, exp: dict, faltan: List[str]) -> None:
    pais = _pais(exp.get("dom_pais") or "MX") or "MX"
    td = _nodo(padre, "tipo_domicilio")
    calle = _limpia(exp.get("dom_calle"), _DIRECCION, 100)
    num = _limpia(exp.get("dom_num_ext"), _DIRECCION, 56)
    col = _limpia(exp.get("dom_colonia"), _DIRECCION, 50)
    nint = _limpia(exp.get("dom_num_int"), _DIRECCION, 40)
    if pais == "MX":
        cp = _cp(exp.get("dom_cp"))
        for etiqueta, v in (("calle", calle), ("número exterior", num), ("colonia", col), ("código postal", cp)):
            if not v:
                faltan.append(f"{etiqueta} del domicilio del cliente")
        n = _nodo(td, "nacional")
        _nodo(n, "colonia", col or "XXXX")
        _nodo(n, "calle", calle or "XXXX")
        _nodo(n, "numero_exterior", num or "SN")
        _opcional(n, "numero_interior", nint)
        _nodo(n, "codigo_postal", cp or "00000")
        return
    e = _nodo(td, "extranjero")
    _nodo(e, "pais", pais)
    _nodo(e, "estado_provincia", _limpia(exp.get("dom_estado"), _DIRECCION, 100) or "XXXX")
    _nodo(e, "ciudad_poblacion", _limpia(exp.get("dom_municipio"), _DIRECCION, 100) or "XXXX")
    _nodo(e, "colonia", col or "XXXX")
    _nodo(e, "calle", calle or "XXXX")
    _nodo(e, "numero_exterior", num or "SN")
    _opcional(e, "numero_interior", nint)
    cpx = re.sub(r"[^A-ZÑ0-9]", "", _plano(exp.get("dom_cp")))[:12]
    if len(cpx) < 4:
        faltan.append("código postal del domicilio extranjero del cliente")
    _nodo(e, "codigo_postal", cpx if len(cpx) >= 4 else "0000")


def _telefono(padre, exp: dict) -> None:
    tel = re.sub(r"\D", "", str(exp.get("telefono") or ""))
    correo = str(exp.get("email") or "").strip().upper()
    tel_ok = 10 <= len(tel) <= 12
    correo_ok = bool(re.fullmatch(r"[A-Z\d\._'\-]+@[A-Z\d_'\-]+\.[A-Z\d\._'\-]+", correo)) and 5 <= len(correo) <= 60
    if not (tel_ok or correo_ok):
        return
    t = _nodo(padre, "telefono")
    if tel_ok:
        _nodo(t, "clave_pais", "MX")
        _nodo(t, "numero_telefono", tel)
    if correo_ok:
        _nodo(t, "correo_electronico", correo)


# ── Operación ─────────────────────────────────────────────────────────────

def _datos_operacion(padre, op: dict, contraparte_exp: Optional[dict], faltan: List[str]) -> None:
    ad = op.get("aviso_datos") or {}
    do = _nodo(padre, "datos_operacion")
    fecha = _fecha(op.get("fecha_operacion"))
    if not fecha:
        faltan.append("fecha de la operación")
    _nodo(do, "fecha_operacion", fecha or "00000000")
    _nodo(do, "tipo_operacion", TIPO_OPERACION_INM)

    fc = str(ad.get("figura_cliente") or "")
    fso = str(ad.get("figura_so") or FIGURA_INTERMEDIARIO)
    if fc not in _claves("figura_cliente"):
        faltan.append("si el cliente es comprador o vendedor")
        fc = "1"
    if fso not in _claves("figura_so"):
        fso = FIGURA_INTERMEDIARIO
    if fso == fc:
        faltan.append("tu papel en la operación no puede ser el mismo que el del cliente")
    _nodo(do, "figura_cliente", fc)
    _nodo(do, "figura_so", fso)

    contrapartes = [c for c in (ad.get("contrapartes") or []) if isinstance(c, dict)]
    if contraparte_exp:
        contrapartes.insert(0, contraparte_exp)
    if fso == FIGURA_INTERMEDIARIO and not contrapartes:
        faltan.append("los datos de la otra parte (vendedor o comprador), porque actúas como intermediario")
    for c in contrapartes:
        _persona_simple(_nodo(do, "datos_contraparte"), c, faltan, "la otra parte")

    inm = ad.get("inmueble") or {}
    ci = _nodo(do, "caracteristicas_inmueble")
    tipo_inm = str(inm.get("tipo_inmueble") or "")
    if tipo_inm not in _claves("tipo_inmueble"):
        faltan.append("tipo de inmueble")
        tipo_inm = "99"
    _nodo(ci, "tipo_inmueble", tipo_inm)
    valor = _monto(inm.get("valor_pactado") or op.get("monto"))
    if not valor:
        faltan.append("valor pactado del inmueble")
    _nodo(ci, "valor_pactado", valor or "0.00")
    icol = _limpia(inm.get("colonia"), _DIRECCION, 50)
    icalle = _limpia(inm.get("calle"), _DIRECCION, 100)
    inum = _limpia(inm.get("numero_exterior"), _DIRECCION, 56)
    icp = _cp(inm.get("codigo_postal"))
    for etiqueta, v in (("colonia", icol), ("calle", icalle), ("número exterior", inum), ("código postal", icp)):
        if not v:
            faltan.append(f"{etiqueta} del inmueble")
    _nodo(ci, "colonia", icol or "XXXX")
    _nodo(ci, "calle", icalle or "XXXX")
    _nodo(ci, "numero_exterior", inum or "SN")
    _opcional(ci, "numero_interior", _limpia(inm.get("numero_interior"), _DIRECCION, 40))
    _nodo(ci, "codigo_postal", icp or "00000")
    for campo, etiqueta in (("dimension_terreno", "m² de terreno"), ("dimension_construido", "m² de construcción")):
        v = _monto(inm.get(campo), enteros=7)
        if inm.get(campo) in (None, "") or not v:
            faltan.append(f"{etiqueta} del inmueble (pon 0 si no aplica)")
        _nodo(ci, campo, v or "0.00")
    _nodo(ci, "folio_real", _limpia(inm.get("folio_real"), _FOLIO, 200) or "XXXX")

    ins = ad.get("instrumento") or {}
    cip = _nodo(do, "contrato_instrumento_publico")
    if (ins.get("tipo") or "publico") == "contrato":
        fcon = _fecha(ins.get("fecha_contrato"))
        if not fcon:
            faltan.append("fecha del contrato privado")
        _nodo(_nodo(cip, "datos_contrato"), "fecha_contrato", fcon or "00000000")
    else:
        dip = _nodo(cip, "datos_instrumento_publico")
        num = _limpia(ins.get("numero"), _FOLIO, 20)
        fins = _fecha(ins.get("fecha"))
        notario = _limpia(ins.get("notario"), _FOLIO, 8)
        entidad = str(ins.get("entidad") or "")
        avaluo = _monto(ins.get("avaluo_catastral"))
        for etiqueta, v in (("número de escritura", num), ("fecha de escritura", fins),
                            ("número de notario", notario), ("valor del avalúo catastral", avaluo)):
            if not v:
                faltan.append(etiqueta)
        if entidad not in _claves("entidad_federativa"):
            faltan.append("entidad federativa del notario")
            entidad = "01"
        _nodo(dip, "numero_instrumento_publico", num or "0")
        _nodo(dip, "fecha_instrumento_publico", fins or "00000000")
        _nodo(dip, "notario_instrumento_publico", notario or "0")
        _nodo(dip, "entidad_instrumento_publico", entidad)
        _nodo(dip, "valor_avaluo_catastral", avaluo or "0.00")

    liqs = [x for x in (ad.get("liquidaciones") or []) if isinstance(x, dict)]
    if not liqs and fso != FIGURA_INTERMEDIARIO:
        faltan.append("al menos un pago (datos de liquidación)")
    for i, lq in enumerate(liqs, 1):
        dl = _nodo(do, "datos_liquidacion")
        fp = _fecha(lq.get("fecha_pago"))
        forma = str(lq.get("forma_pago") or "")
        inst = str(lq.get("instrumento_monetario") or "")
        moneda = str(lq.get("moneda") or "1")
        monto = _monto(lq.get("monto"))
        if not fp:
            faltan.append(f"fecha del pago {i}")
        if forma not in _claves("forma_pago"):
            faltan.append(f"forma de pago del pago {i}")
            forma = "1"
        if forma in ("1", "2", "5") and inst not in _claves("instrumento_monetario"):
            faltan.append(f"instrumento monetario del pago {i}")
        if forma == "5" and inst not in ("16", "99"):
            faltan.append(f"en una permuta el instrumento del pago {i} solo puede ser activos virtuales u otros")
        if moneda not in _claves("moneda"):
            faltan.append(f"moneda del pago {i}")
            moneda = "1"
        if not monto:
            faltan.append(f"monto del pago {i}")
        _nodo(dl, "fecha_pago", fp or "00000000")
        _nodo(dl, "forma_pago", forma)
        _opcional(dl, "instrumento_monetario", inst if inst in _claves("instrumento_monetario") else "")
        _nodo(dl, "moneda", moneda)
        _nodo(dl, "monto_operacion", monto or "0.00")


def construir_xml(cfg: dict, periodo: str, operaciones: List[dict],
                  expedientes: Dict[str, dict]) -> Tuple[str, List[str]]:
    """Devuelve (xml, problemas). Si hay problemas, el XML no se debe entregar."""
    problemas: List[str] = []
    ET.register_namespace("", NS)
    raiz = ET.Element(f"{{{NS}}}archivo")
    inf = _nodo(raiz, "informe")
    mes = re.sub(r"\D", "", periodo or "")[:6]
    if not re.fullmatch(r"\d{4}(0[1-9]|1[0-2])", mes):
        problemas.append("El periodo debe ir como 2026-03.")
    _nodo(inf, "mes_reportado", mes)

    so = _nodo(inf, "sujeto_obligado")
    colegiada = _rfc(cfg.get("clave_entidad_colegiada"), True)
    _opcional(so, "clave_entidad_colegiada", colegiada)
    clave = _rfc(cfg.get("rfc_sujeto_obligado"), False) or _rfc(cfg.get("rfc_sujeto_obligado"), True)
    if not clave:
        problemas.append("Ajustes: falta tu RFC con homoclave como sujeto obligado "
                         "(es la clave con la que te identificas ante el SAT).")
    _nodo(so, "clave_sujeto_obligado", clave or "XXXX000000XXX")
    _nodo(so, "clave_actividad", "INM")

    for op in operaciones:
        faltan: List[str] = []
        exp = expedientes.get(op.get("expediente_id")) or {}
        etiqueta = f"Operación del {str(op.get('fecha_operacion') or '')[:10]} con {nombre_de(exp)}"
        if (op.get("tipo_operacion") or "compraventa") not in TIPOS_BROQUER_INM:
            problemas.append(f"{etiqueta}: el arrendamiento es otra actividad vulnerable "
                             f"(fracción XV) y no puede ir en el aviso de inmuebles.")
            continue
        ad = op.get("aviso_datos") or {}
        a = _nodo(inf, "aviso")
        _nodo(a, "referencia_aviso", _referencia(op.get("id")) or "1")
        # Aviso modificatorio: corrige uno ya aceptado. Lleva el folio que la
        # UIF le dio en el acuse (AAAA-999999999) y qué se cambió.
        mod = op.get("_modificatorio")
        if mod:
            folio = str(mod.get("folio") or "").strip()
            desc = _limpia(mod.get("descripcion"), _DESCRIPCION, 3000)
            if not re.fullmatch(r"\d{4}-[1-9]\d{0,8}", folio):
                faltan.append("el folio del aviso original como aparece en tu acuse (ej. 2026-1234)")
            if not desc:
                faltan.append("qué se corrige en el aviso modificatorio")
            m = _nodo(a, "modificatorio")
            _nodo(m, "folio_modificacion", folio if re.fullmatch(r"\d{4}-[1-9]\d{0,8}", folio) else "0000-1")
            _nodo(m, "descripcion_modificacion", desc or "X")
        prioridad = "2" if op.get("inusual") else "1"
        _nodo(a, "prioridad", prioridad)
        al = _nodo(a, "alerta")
        tipo_alerta = str(ad.get("tipo_alerta") or (ALERTA_OTRA if op.get("inusual") else ALERTA_SIN_ALERTA))
        if tipo_alerta not in _claves("tipo_alerta"):
            faltan.append("tipo de alerta (elige una del catálogo)")
            tipo_alerta = ALERTA_OTRA
        if prioridad == "2" and tipo_alerta == ALERTA_SIN_ALERTA:
            faltan.append("una operación inusual (24 horas) no puede ir con \"Sin alerta\"")
        _nodo(al, "tipo_alerta", tipo_alerta)
        desc = _limpia(ad.get("descripcion_alerta") or op.get("inusual_motivo"), _DESCRIPCION, 3000)
        if tipo_alerta == ALERTA_OTRA and not desc:
            faltan.append("descripción de la alerta")
        _opcional(al, "descripcion_alerta", desc)

        pa = _nodo(a, "persona_aviso")
        _persona_aviso(pa, exp, faltan)
        if (exp.get("tipo_persona") or "fisica") in ("fisica", "moral"):
            _domicilio(pa, exp, faltan)
        _telefono(pa, exp)

        if exp.get("bc_es_el_mismo") is False:
            bc = {"tipo_persona": "fisica", "nombre": exp.get("bc_nombre"),
                  "apellido_paterno": exp.get("bc_apellido_paterno"),
                  "apellido_materno": exp.get("bc_apellido_materno"),
                  "fecha_nacimiento": exp.get("bc_fecha_nacimiento"),
                  "rfc": exp.get("bc_rfc"), "curp": exp.get("bc_curp")}
            _persona_simple(_nodo(a, "dueno_beneficiario"), bc, faltan, "el dueño beneficiario")

        det = _nodo(a, "detalle_operaciones")
        _datos_operacion(det, op, expedientes.get(op.get("contraparte_exp_id")), faltan)

        if faltan:
            problemas.append(f"{etiqueta}: falta " + "; ".join(dict.fromkeys(faltan)) + ".")

    xml = ET.tostring(raiz, encoding="unicode")
    return con_ubicacion_esquema('<?xml version="1.0" encoding="UTF-8"?>\n' + xml), problemas


_RAIZ_SIN_ESQUEMA = f'<archivo xmlns="{NS}">'
_RAIZ_OFICIAL = (f'<archivo xsi:schemaLocation="{NS} inm.xsd" '
                 f'xmlns="{NS}" xmlns:xsi="{XSI}">')


def con_ubicacion_esquema(xml: str) -> str:
    """La raíz debe declarar xsi:schemaLocation como en el ejemplo oficial.

    El validador del portal de la UIF busca el esquema con ese atributo; sin
    él rechaza el archivo con «cvc-elt.1: Cannot find the declaration of
    element 'archivo'», aunque el contenido esté bien. También sirve para
    reparar archivos que ya se habían guardado sin él."""
    return xml.replace(_RAIZ_SIN_ESQUEMA, _RAIZ_OFICIAL, 1)


@lru_cache(maxsize=1)
def _esquema():
    from lxml import etree
    return etree.XMLSchema(etree.parse(str(XSD_PATH)))


def validar_xsd(xml: str) -> List[str]:
    """Errores del XML contra el XSD oficial (lista vacía = válido)."""
    from lxml import etree
    esquema = _esquema()
    doc = etree.fromstring(xml.encode("utf-8"))
    if esquema.validate(doc):
        return []
    return [f"línea {e.line}: {e.message}" for e in esquema.error_log][:20]
