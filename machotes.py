"""
machotes.py — Motor de machotes propios de Broquer.

Convierte cualquier contrato .docx que suba el usuario en una plantilla real:

  1. EXTRACCIÓN   Recorre cuerpo, tablas anidadas, encabezados, pies y cuadros
                  de texto, conservando la posición exacta de cada run.
  2. DETECCIÓN    a) Marcadores explícitos: {{campo}}, [[campo]], <<campo>>,
                     «campo», {campo}, [CAMPO], XXXX, y blancos (___ / .....).
                  b) Contrato real sin marcar: Claude identifica las variables
                     y devuelve el literal EXACTO de cada una; se verifica
                     contra el documento antes de aceptarlo (cero alucinación).
  3. NORMALIZACIÓN Reescribe el DOCX sustituyendo cada variable por {{id}}.
                  El machote guardado ya es una plantilla marcada, así que el
                  relleno posterior es determinista.
  4. RELLENO      Sustituye {{id}} respetando el formato original (negritas,
                  tamaños, subrayados) aun cuando Word parte el marcador en
                  varios runs.

Todo el módulo es puro (sin FastAPI, sin Supabase) para poder probarse aislado.
"""

import io
import re
import unicodedata
import json as _json
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ────────────────────────────────────────────────────────────────
# CONSTANTES
# ────────────────────────────────────────────────────────────────

ANTHROPIC_BASE = "https://api.anthropic.com/v1"
MODELO_DEFAULT = "claude-sonnet-4-6"

# Tamaño de trozo para el análisis con IA (caracteres). Los trozos se procesan
# en paralelo y se fusionan por literal.
CHUNK_CHARS = 22000
CHUNK_OVERLAP = 1200
MAX_CHARS_TOTAL = 400000

# Un literal que aparece más veces que esto casi siempre es texto de boilerplate
# mal identificado (ej. "EL ARRENDADOR"), no un dato variable.
MAX_OCURRENCIAS_LITERAL = 40

TIPOS_INPUT = {"text", "textarea", "number", "currency", "date"}

# Literales que jamás son variables aunque la IA insista.
_BLOQUEADOS = {
    "el vendedor", "la vendedora", "el comprador", "la compradora",
    "el arrendador", "la arrendadora", "el arrendatario", "la arrendataria",
    "el promitente", "las partes", "la parte", "el inmueble", "el contrato",
    "pesos", "moneda nacional", "m.n.", "mn", "iva", "s.a. de c.v.",
    "estados unidos mexicanos", "codigo civil", "primera", "segunda",
    "tercera", "cuarta", "quinta", "sexta", "declaraciones", "clausulas",
    "clausula", "vendedor", "comprador", "arrendador", "arrendatario",
    "testigo", "testigos", "fiador", "obligado solidario", "si", "no",
}

_NUM_LETRAS_UNIDADES = [
    "", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO",
    "NUEVE", "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE",
    "DIECISÉIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE",
    "VEINTIUNO", "VEINTIDÓS", "VEINTITRÉS", "VEINTICUATRO", "VEINTICINCO",
    "VEINTISÉIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE",
]
_NUM_LETRAS_DECENAS = [
    "", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA",
    "OCHENTA", "NOVENTA",
]
_NUM_LETRAS_CENTENAS = [
    "", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
    "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS",
]


# ────────────────────────────────────────────────────────────────
# UTILIDADES DE TEXTO
# ────────────────────────────────────────────────────────────────

def _sin_acentos(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    )


def slug_campo(nombre: str, usados: Optional[set] = None) -> str:
    """Convierte 'Nombre del Arrendatario' -> 'nombre_del_arrendatario'."""
    s = _sin_acentos(nombre or "").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    s = s[:48] or "campo"
    if s[0].isdigit():
        s = "c_" + s
    if usados is not None:
        base, i = s, 2
        while s in usados:
            s = f"{base}_{i}"
            i += 1
        usados.add(s)
    return s


def humanizar(nombre: str) -> str:
    """'nombre_del_arrendatario' -> 'Nombre del arrendatario'."""
    s = re.sub(r"[_\-]+", " ", (nombre or "").strip())
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return "Campo"
    if s.lower() in _ACRONIMOS:
        return s.upper()
    if s.isupper() or s.islower():
        s = s.capitalize()
    return " ".join(
        (w.upper() if w.lower().strip(".,") in _ACRONIMOS else w) for w in s.split()
    )


def _regex_flexible(literal: str) -> re.Pattern:
    """Regex que tolera diferencias de espaciado/saltos respecto al literal."""
    partes = [re.escape(t) for t in literal.split() if t]
    if not partes:
        return re.compile(re.escape(literal))
    return re.compile(r"\s+".join(partes))


def numero_a_letras(valor, moneda: str = "PESOS", sufijo: str = "M.N.") -> str:
    """8500 -> 'OCHO MIL QUINIENTOS PESOS 00/100 M.N.'"""
    try:
        limpio = re.sub(r"[^0-9.\-]", "", str(valor or "").replace(",", ""))
        num = abs(float(limpio))
    except Exception:
        return ""
    entero = int(num)
    centavos = int(round((num - entero) * 100))
    if centavos == 100:
        entero += 1
        centavos = 0
    letras = _entero_a_letras(entero)
    if not letras:
        return ""
    # Apócope: "veintiuno pesos" no existe -> "veintiún pesos".
    if letras.endswith("VEINTIUNO"):
        letras = letras[:-9] + "VEINTIÚN"
    elif letras.endswith("UNO"):
        letras = letras[:-3] + "UN"
    partes = [letras]
    if moneda:
        m = moneda.upper()
        if entero == 1 and m.endswith("S"):
            m = m[:-1]
        # "un millón DE pesos", pero "un millón quinientos mil pesos".
        if entero >= 1_000_000 and entero % 1_000_000 == 0:
            m = "DE " + m
        partes.append(m)
    partes.append(f"{centavos:02d}/100")
    if sufijo:
        partes.append(sufijo)
    return " ".join(partes)


def _centena_a_letras(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "CIEN"
    out = []
    c, resto = divmod(n, 100)
    if c:
        out.append(_NUM_LETRAS_CENTENAS[c])
    if resto:
        if resto < 30:
            out.append(_NUM_LETRAS_UNIDADES[resto])
        else:
            d, u = divmod(resto, 10)
            out.append(_NUM_LETRAS_DECENAS[d] + (f" Y {_NUM_LETRAS_UNIDADES[u]}" if u else ""))
    return " ".join(p for p in out if p)


def _entero_a_letras(n: int) -> str:
    if n == 0:
        return "CERO"
    if n >= 1_000_000_000_000:
        return str(n)
    out = []
    millones, resto = divmod(n, 1_000_000)
    if millones:
        if millones == 1:
            out.append("UN MILLÓN")
        else:
            out.append(_entero_a_letras(millones) + " MILLONES")
    miles, cientos = divmod(resto, 1000)
    if miles:
        out.append("MIL" if miles == 1 else _centena_a_letras(miles) + " MIL")
    if cientos:
        out.append(_centena_a_letras(cientos))
    return " ".join(p for p in out if p).strip()


# ────────────────────────────────────────────────────────────────
# RECORRIDO DEL DOCX
# ────────────────────────────────────────────────────────────────

def _runs_de_parrafo(p):
    """Runs reales del párrafo, incluyendo los que viven dentro de hipervínculos,
    marcas de revisión o smart tags. Excluye los de cuadros de texto anidados
    (esos se recorren como párrafos propios)."""
    from docx.text.run import Run
    xs = p._p.xpath(
        "./w:r | ./w:hyperlink/w:r | ./w:ins/w:r | ./w:smartTag/w:r "
        "| ./w:hyperlink/w:ins/w:r | ./w:sdt/w:sdtContent/w:r"
    )
    return [Run(r, p) for r in xs]


def _parrafos_de_celda(cell):
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.ns import qn
    for hijo in cell._tc.iterchildren():
        if hijo.tag == qn("w:p"):
            yield Paragraph(hijo, cell)
        elif hijo.tag == qn("w:tbl"):
            tabla = Table(hijo, cell)
            for fila in tabla.rows:
                for c in fila.cells:
                    yield from _parrafos_de_celda(c)


def _parrafos_de_contenedor(cont):
    """Párrafos de un body/header/footer en orden real, entrando a las tablas."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.ns import qn
    elem = getattr(cont, "element", None)
    if elem is None:
        elem = cont._element
    cuerpo = elem.body if hasattr(elem, "body") else elem
    for hijo in cuerpo.iterchildren():
        if hijo.tag == qn("w:p"):
            yield Paragraph(hijo, cont)
        elif hijo.tag == qn("w:tbl"):
            tabla = Table(hijo, cont)
            for fila in tabla.rows:
                for c in fila.cells:
                    yield from _parrafos_de_celda(c)


def _parrafos_de_cuadros_texto(cont):
    from docx.text.paragraph import Paragraph
    elem = getattr(cont, "element", None)
    if elem is None:
        elem = cont._element
    try:
        for p in elem.xpath(".//w:txbxContent//w:p"):
            yield Paragraph(p, cont)
    except Exception:
        return


def iter_parrafos(doc):
    """Todos los párrafos del documento: cuerpo, tablas, encabezados, pies y
    cuadros de texto. Orden estable entre llamadas."""
    vistos = set()

    def _emitir(p):
        pid = id(p._p)
        if pid in vistos:
            return None
        vistos.add(pid)
        return p

    for p in _parrafos_de_contenedor(doc):
        if _emitir(p) is not None:
            yield p
    for p in _parrafos_de_cuadros_texto(doc):
        if _emitir(p) is not None:
            yield p
    for sec in doc.sections:
        for cont in (sec.header, sec.footer, sec.first_page_header,
                     sec.first_page_footer, sec.even_page_header,
                     sec.even_page_footer):
            if cont is None:
                continue
            try:
                for p in _parrafos_de_contenedor(cont):
                    if _emitir(p) is not None:
                        yield p
                for p in _parrafos_de_cuadros_texto(cont):
                    if _emitir(p) is not None:
                        yield p
            except Exception:
                continue


def _texto_runs(runs) -> str:
    return "".join(r.text or "" for r in runs)


def cargar_docx(content: bytes):
    from docx import Document as DocxDocument
    return DocxDocument(io.BytesIO(content))


def snapshot(doc) -> List[Dict[str, Any]]:
    """[{'p': Paragraph, 'runs': [...], 'texto': str}] para todo el documento."""
    out = []
    for p in iter_parrafos(doc):
        runs = _runs_de_parrafo(p)
        out.append({"p": p, "runs": runs, "texto": _texto_runs(runs)})
    return out


def texto_completo(snap: List[Dict[str, Any]]) -> str:
    return "\n".join(s["texto"] for s in snap if (s["texto"] or "").strip())


# ────────────────────────────────────────────────────────────────
# MOTOR DE SUSTITUCIÓN A NIVEL RUN (conserva formato)
# ────────────────────────────────────────────────────────────────

def aplicar_spans(runs, spans: List[Tuple[int, int, str]]) -> bool:
    """Sustituye los rangos [inicio, fin) del texto concatenado del párrafo por
    su valor, tocando solo los runs afectados.

    El texto insertado hereda el formato del run donde empieza el marcador, que
    es exactamente lo que Word haría. Los runs no afectados quedan intactos.
    """
    if not runs or not spans:
        return False

    textos = [r.text or "" for r in runs]
    inicios, acc = [], 0
    for t in textos:
        inicios.append(acc)
        acc += len(t)
    total = acc

    def localizar(idx: int) -> Optional[Tuple[int, int]]:
        for i, t in enumerate(textos):
            if t and inicios[i] <= idx < inicios[i] + len(t):
                return i, idx - inicios[i]
        return None

    spans = sorted(spans, key=lambda s: s[0])
    cambio = False
    for inicio, fin, valor in reversed(spans):
        if inicio < 0 or fin > total or fin <= inicio:
            continue
        a = localizar(inicio)
        b = localizar(fin - 1)
        if a is None or b is None:
            continue
        ri, off_a = a
        rf, off_b = b
        off_b += 1
        if ri == rf:
            t = textos[ri]
            textos[ri] = t[:off_a] + valor + t[off_b:]
        else:
            textos[ri] = textos[ri][:off_a] + valor
            for k in range(ri + 1, rf):
                textos[k] = ""
            textos[rf] = textos[rf][off_b:]
        cambio = True

    if cambio:
        for r, t in zip(runs, textos):
            if (r.text or "") != t:
                r.text = t
    return cambio


# ────────────────────────────────────────────────────────────────
# DETECCIÓN DE MARCADORES EXPLÍCITOS
# ────────────────────────────────────────────────────────────────

_RE_LLAVES_DOBLES = re.compile(r"\{\{\s*([^{}]{1,80}?)\s*\}\}")
_RE_CORCH_DOBLES = re.compile(r"\[\[\s*([^\[\]]{1,80}?)\s*\]\]")
_RE_ANGULOS = re.compile(r"<<\s*([^<>]{1,80}?)\s*>>")
_RE_GUILLEMET = re.compile(r"«\s*([^«»]{1,80}?)\s*»")
_RE_LLAVES = re.compile(r"\{\s*([^{}]{1,80}?)\s*\}")
_RE_CORCHETES = re.compile(r"\[\s*([^\[\]]{1,80}?)\s*\]")
_RE_BLANCO = re.compile(r"(?:_{3,}|\.{6,}|X{4,})")

_MARCADORES = [
    ("llaves_dobles", _RE_LLAVES_DOBLES),
    ("corchetes_dobles", _RE_CORCH_DOBLES),
    ("angulos", _RE_ANGULOS),
    ("guillemets", _RE_GUILLEMET),
    ("llaves", _RE_LLAVES),
    ("corchetes", _RE_CORCHETES),
]


def _corchete_valido(contenido: str) -> bool:
    """[NOMBRE DEL VENDEDOR] sí. [1] o [sic] o [Ley Federal...] no."""
    c = contenido.strip()
    if not c or len(c) < 2 or c.isdigit():
        return False
    letras = [ch for ch in _sin_acentos(c) if ch.isalpha()]
    if not letras:
        return False
    minusculas = sum(1 for ch in letras if ch.islower())
    if minusculas == 0:
        return len(letras) >= 2          # [NOMBRE DEL VENDEDOR]
    plano = _sin_acentos(c)
    if "_" in plano and re.fullmatch(r"[a-z0-9_\.\-]+", plano):
        return True                       # [nombre_del_vendedor]
    if len(c.split()) >= 2 and re.fullmatch(r"[A-Za-z0-9 _\.\-]+", plano):
        return True                       # [nombre del vendedor]
    return False                          # [sic], [id], [ibid], [Ley...]


def detectar_marcadores(snap: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Busca marcadores explícitos. Devuelve campos + los spans a normalizar."""
    for nombre, rx in _MARCADORES:
        hits = []
        for i, s in enumerate(snap):
            for m in rx.finditer(s["texto"]):
                contenido = (m.group(1) or "").strip()
                if not contenido:
                    continue
                if nombre == "corchetes" and not _corchete_valido(contenido):
                    continue
                if nombre == "llaves" and len(contenido) > 60:
                    continue
                hits.append((i, m.start(), m.end(), contenido))
        if not hits:
            continue

        usados, por_nombre, campos = set(), {}, []
        spans: Dict[int, List[Tuple[int, int, str]]] = {}
        for i, ini, fin, contenido in hits:
            clave = _sin_acentos(contenido).lower().strip()
            if clave not in por_nombre:
                cid = slug_campo(contenido, usados)
                por_nombre[clave] = cid
                campos.append({
                    "id": cid,
                    "label": humanizar(contenido),
                    "tipo_input": "text",
                    "grupo": "Datos del contrato",
                    "ejemplo": "",
                    "ocurrencias": 0,
                    "origen": nombre,
                })
            cid = por_nombre[clave]
            for c in campos:
                if c["id"] == cid:
                    c["ocurrencias"] += 1
                    break
            spans.setdefault(i, []).append((ini, fin, "{{" + cid + "}}"))
        return {"campos": campos, "spans": spans, "motor": "marcadores",
                "patron": nombre}

    return {"campos": [], "spans": {}, "motor": None, "patron": None}


def detectar_blancos(snap: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Cada línea ___ / ..... / XXXX se convierte en un campo independiente,
    con etiqueta provisional tomada del texto que la precede."""
    campos, spans, usados = [], {}, set()
    n = 0
    for i, s in enumerate(snap):
        texto = s["texto"]
        for m in _RE_BLANCO.finditer(texto):
            n += 1
            previo = texto[:m.start()]
            etiqueta = _etiqueta_desde_contexto(previo, snap, i)
            cid = slug_campo(etiqueta or f"campo {n}", usados)
            campos.append({
                "id": cid,
                "label": humanizar(etiqueta) if etiqueta else f"Campo {n}",
                "tipo_input": "text",
                "grupo": "Datos del contrato",
                "ejemplo": "",
                "ocurrencias": 1,
                "origen": "blanco",
                "contexto": (previo[-90:] + " ______ " + texto[m.end():m.end() + 40]).strip(),
            })
            spans.setdefault(i, []).append((m.start(), m.end(), "{{" + cid + "}}"))
    if not campos:
        return {"campos": [], "spans": {}, "motor": None, "patron": None}
    return {"campos": campos, "spans": spans, "motor": "blancos", "patron": "blanco"}


_ACRONIMOS = {"rfc", "curp", "cp", "c.p.", "ine", "ife", "m2", "iva", "isr",
              "clabe", "cfdi", "sat", "id"}


def _etiqueta_desde_contexto(previo: str, snap, i: int) -> str:
    """De 'RFC: ______ CURP: ' saca 'CURP' — corta siempre en el blanco previo."""
    t = (previo or "")
    t = _RE_BLANCO.split(t)[-1]                       # solo lo que sigue al blanco anterior
    if not t.strip() and i > 0:
        t = _RE_BLANCO.split(snap[i - 1]["texto"] or "")[-1]
    t = re.split(r"[.;•]|\s{3,}", t)[-1]
    t = t.strip().rstrip(" :;,.-—–$()[]")
    t = re.sub(r"^[\s:;,.\-—–\d)°º]+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    palabras = t.split()
    if len(palabras) > 7:
        t = " ".join(palabras[-7:])
    return t if len(t) >= 3 else ""


# ────────────────────────────────────────────────────────────────
# CLAUDE
# ────────────────────────────────────────────────────────────────

async def _claude(api_key: str, system: str, user: str,
                  max_tokens: int = 8000, modelo: str = MODELO_DEFAULT) -> Tuple[str, dict]:
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": modelo,
                "max_tokens": max_tokens,
                "temperature": 0,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
    if r.status_code != 200:
        raise RuntimeError(f"Anthropic {r.status_code}: {r.text[:300]}")
    data = r.json()
    txt = "".join(b.get("text", "") for b in data.get("content", [])
                  if b.get("type") == "text")
    return txt, data


def _json_de_respuesta(txt: str) -> dict:
    t = (txt or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.MULTILINE).strip()
    try:
        return _json.loads(t)
    except Exception:
        pass
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if m:
        try:
            return _json.loads(m.group())
        except Exception:
            pass
    return {}


def _trozos(texto: str) -> List[str]:
    texto = texto[:MAX_CHARS_TOTAL]
    if len(texto) <= CHUNK_CHARS:
        return [texto]
    out, i = [], 0
    while i < len(texto):
        fin = min(i + CHUNK_CHARS, len(texto))
        if fin < len(texto):
            corte = texto.rfind("\n", i + int(CHUNK_CHARS * 0.6), fin)
            if corte > i:
                fin = corte
        out.append(texto[i:fin])
        if fin >= len(texto):
            break
        i = max(fin - CHUNK_OVERLAP, i + 1)
    return out


_SYSTEM_DETECCION = """Eres un abogado mexicano experto en contratos inmobiliarios que prepara plantillas.

Tu trabajo: leer un contrato REAL ya lleno y señalar qué datos son VARIABLES, es decir, los que cambian cada vez que se usa el contrato con otro cliente.

SÍ son variables:
- Nombres de personas y de empresas (partes, representantes, testigos, fiadores, obligados solidarios, notarios).
- RFC, CURP, identificaciones oficiales, números de escritura, de notaría, de folio real, de cuenta predial o catastral.
- Domicilios completos y también sus partes (calle, número, colonia, código postal, municipio, estado).
- Fechas (de firma, de inicio, de vencimiento, de entrega).
- Montos con cifra ($8,500.00) y el MISMO monto escrito con letra (OCHO MIL QUINIENTOS PESOS 00/100 M.N.) — son DOS campos distintos.
- Plazos, vigencias, número de meses, porcentajes, penalizaciones.
- Superficies, medidas, colindancias, número de estacionamientos, descripción del inmueble.
- Datos bancarios, correos, teléfonos.
- Ciudad y fecha en que se firma.

NO son variables:
- El texto de las cláusulas, declaraciones y obligaciones.
- Referencias a leyes, códigos y artículos.
- Etiquetas de rol genéricas como "EL ARRENDADOR", "EL COMPRADOR", "LAS PARTES".
- Palabras sueltas o frases comunes que se repiten como boilerplate.

REGLA ABSOLUTA sobre "literal": debes copiar el texto EXACTAMENTE como aparece en el documento, carácter por carácter, con sus acentos, mayúsculas, puntuación y símbolos. No lo corrijas, no lo traduzcas, no lo abrevies, no lo completes. Si no puedes copiarlo exacto, no incluyas ese campo. El literal debe ser el VALOR concreto (ej. "JUAN PÉREZ LÓPEZ"), nunca la etiqueta que lo antecede (ej. no "Nombre del arrendador:").

Un mismo dato puede aparecer varias veces en el contrato: repórtalo UNA sola vez.

Responde ÚNICAMENTE con JSON válido, sin explicaciones ni markdown:
{"campos":[{"id":"snake_case","label":"Etiqueta en español natural","tipo_input":"text|textarea|number|currency|date","grupo":"Nombre del bloque","literal":"texto exacto del documento","ayuda":"pista corta para el usuario, opcional"}]}

- "id": snake_case, sin acentos, descriptivo y único (ej. nombre_arrendador, renta_mensual, renta_mensual_letra).
- "label": cómo se lo pedirías al agente inmobiliario. Empieza con mayúscula, sin dos puntos al final.
- "grupo": agrupa los campos por bloque lógico ("Arrendador", "Arrendatario", "Inmueble", "Renta y depósito", "Vigencia", "Firma", "Testigos"). Usa pocos grupos y repítelos.
- "tipo_input": "currency" solo para importes en cifra; "date" solo para fechas completas; "number" para cantidades; "textarea" para descripciones largas; "text" para el resto."""

_SYSTEM_ETIQUETAS = """Eres un abogado mexicano experto en contratos. Recibes un contrato que ya tiene marcadores de variable con el formato {{id}}.

Tu trabajo: para cada {{id}} que aparezca, deducir por el contexto qué dato hay que capturar ahí y darle una etiqueta clara, un tipo de dato y un grupo.

Responde ÚNICAMENTE con JSON válido, sin explicaciones ni markdown:
{"campos":[{"id":"id_exacto_del_marcador","label":"Etiqueta en español natural","tipo_input":"text|textarea|number|currency|date","grupo":"Nombre del bloque","ayuda":"pista corta, opcional","descartar":false}]}

- Usa EXACTAMENTE los mismos id que ya vienen entre llaves. No inventes ids nuevos ni omitas ninguno.
- "label": cómo se lo pedirías al agente inmobiliario (ej. "Nombre completo del arrendatario", "Renta mensual con letra").
- "grupo": bloque lógico ("Arrendador", "Arrendatario", "Inmueble", "Renta y depósito", "Vigencia", "Firma", "Testigos"). Usa pocos grupos y repítelos.
- "tipo_input": "currency" para importes en cifra; "date" para fechas; "number" para cantidades; "textarea" para descripciones largas; "text" para el resto.
- "descartar": ponlo en true SOLO si ese marcador claramente no es un dato que el usuario deba capturar (por ejemplo una acotación editorial como [sic], una nota al pie o una referencia legal). En cualquier duda, false."""


async def _detectar_ia_trozo(api_key: str, trozo: str, tipo: str, modelo: str):
    hint = f"El documento es un contrato de {tipo}.\n\n" if tipo else ""
    user = f"{hint}Contrato:\n<<<\n{trozo}\n>>>"
    txt, raw = await _claude(api_key, _SYSTEM_DETECCION, user, 8000, modelo)
    return _json_de_respuesta(txt).get("campos") or [], raw


async def detectar_con_ia(api_key: str, texto: str, tipo: str = "",
                          modelo: str = MODELO_DEFAULT):
    """Analiza el contrato completo (en paralelo si es largo) y devuelve campos
    candidatos con su literal, más las respuestas crudas para tracking."""
    import asyncio
    trozos = _trozos(texto)
    resultados = await asyncio.gather(
        *[_detectar_ia_trozo(api_key, t, tipo, modelo) for t in trozos],
        return_exceptions=True,
    )
    campos, raws, errores = [], [], []
    vistos_literal, vistos_id = set(), set()
    for r in resultados:
        if isinstance(r, Exception):
            errores.append(str(r))
            continue
        lista, raw = r
        raws.append(raw)
        for c in lista or []:
            if not isinstance(c, dict):
                continue
            lit = (c.get("literal") or "").strip()
            if not lit:
                continue
            clave = _sin_acentos(lit).lower()
            if clave in vistos_literal:
                continue
            vistos_literal.add(clave)
            cid = slug_campo(c.get("id") or c.get("label") or lit, vistos_id)
            campos.append({
                "id": cid,
                "label": (c.get("label") or humanizar(cid)).strip().rstrip(":"),
                "tipo_input": c.get("tipo_input") if c.get("tipo_input") in TIPOS_INPUT else "text",
                "grupo": (c.get("grupo") or "Datos del contrato").strip(),
                "ayuda": (c.get("ayuda") or "").strip(),
                "literal": lit,
                "origen": "ia",
            })
    if not campos and errores:
        raise RuntimeError(errores[0])
    return campos, raws


async def etiquetar_con_ia(api_key: str, texto_normalizado: str, campos: List[dict],
                           tipo: str = "", modelo: str = MODELO_DEFAULT):
    """Mejora label/tipo/grupo de campos que ya están marcados como {{id}}."""
    hint = f"El documento es un contrato de {tipo}.\n\n" if tipo else ""
    ids = ", ".join(c["id"] for c in campos)
    trozo = texto_normalizado[:CHUNK_CHARS * 2]
    user = (f"{hint}Marcadores presentes: {ids}\n\nContrato con marcadores:\n<<<\n{trozo}\n>>>")
    txt, raw = await _claude(api_key, _SYSTEM_ETIQUETAS, user, 8000, modelo)
    sugeridos = {c.get("id"): c for c in (_json_de_respuesta(txt).get("campos") or [])
                 if isinstance(c, dict) and c.get("id")}
    fuera = {cid for cid, s in sugeridos.items() if s.get("descartar") is True}
    for c in campos:
        s = sugeridos.get(c["id"])
        if not s:
            continue
        label = (s.get("label") or "").strip().rstrip(":")
        if label:
            c["label"] = label
        if s.get("tipo_input") in TIPOS_INPUT:
            c["tipo_input"] = s["tipo_input"]
        if (s.get("grupo") or "").strip():
            c["grupo"] = s["grupo"].strip()
        if (s.get("ayuda") or "").strip():
            c["ayuda"] = s["ayuda"].strip()
    if fuera and len(fuera) < len(campos):
        campos = [c for c in campos if c["id"] not in fuera]
    return campos, [raw]


# ────────────────────────────────────────────────────────────────
# ANCLAJE: verificar los literales de la IA contra el documento real
# ────────────────────────────────────────────────────────────────

def anclar_literales(snap: List[Dict[str, Any]], campos: List[dict]):
    """Localiza cada literal en el documento y produce los spans a normalizar.

    Se procesa de literal más largo a más corto para que "JUAN PÉREZ LÓPEZ" gane
    sobre "JUAN PÉREZ". Un literal que no aparece tal cual se descarta: es la
    garantía de que la IA no invente campos que luego no se pueden rellenar.
    """
    ocupados: Dict[int, List[Tuple[int, int]]] = {}
    spans: Dict[int, List[Tuple[int, int, str]]] = {}
    aceptados, descartados = [], []

    def libre(i, ini, fin) -> bool:
        for a, b in ocupados.get(i, []):
            if ini < b and a < fin:
                return False
        return True

    for c in sorted(campos, key=lambda x: -len(x.get("literal") or "")):
        lit = (c.get("literal") or "").strip()
        clave = _sin_acentos(lit).lower().strip(" .,:;")
        if len(lit) < 2 or clave in _BLOQUEADOS:
            descartados.append({"label": c.get("label"), "literal": lit,
                                "motivo": "texto genérico"})
            continue

        rx = _regex_flexible(lit)
        hallazgos = []
        for i, s in enumerate(snap):
            for m in rx.finditer(s["texto"]):
                hallazgos.append((i, m.start(), m.end()))
        if not hallazgos:
            rx = re.compile(rx.pattern, re.IGNORECASE)
            for i, s in enumerate(snap):
                for m in rx.finditer(s["texto"]):
                    hallazgos.append((i, m.start(), m.end()))
        if not hallazgos:
            descartados.append({"label": c.get("label"), "literal": lit,
                                "motivo": "no aparece en el documento"})
            continue
        if len(hallazgos) > MAX_OCURRENCIAS_LITERAL:
            descartados.append({"label": c.get("label"), "literal": lit,
                                "motivo": "aparece demasiadas veces"})
            continue

        usables = [(i, a, b) for (i, a, b) in hallazgos if libre(i, a, b)]
        if not usables:
            descartados.append({"label": c.get("label"), "literal": lit,
                                "motivo": "contenido dentro de otro campo"})
            continue

        for i, a, b in usables:
            ocupados.setdefault(i, []).append((a, b))
            spans.setdefault(i, []).append((a, b, "{{" + c["id"] + "}}"))
        c = dict(c)
        c["ocurrencias"] = len(usables)
        c["ejemplo"] = lit[:120]
        aceptados.append(c)

    return aceptados, spans, descartados


# ────────────────────────────────────────────────────────────────
# POST-PROCESO DE CAMPOS
# ────────────────────────────────────────────────────────────────

_HINTS_TIPO = [
    (r"\b(fecha|dia de firma|vencimiento|vigencia desde|fecha de inicio)\b", "date"),
    (r"\b(con letra|en letra|letras)\b", "text"),
    (r"\b(renta|monto|precio|importe|deposito|dep[oó]sito|pago|anticipo|"
     r"enganche|penalizaci[oó]n|comisi[oó]n|valor|saldo)\b", "currency"),
    (r"\b(plazo|meses|a[nñ]os|d[ií]as|superficie|metros|m2|cantidad|n[uú]mero de|"
     r"porcentaje|edad)\b", "number"),
    (r"\b(descripci[oó]n|colindancias|observaciones|cl[aá]usula|antecedentes)\b", "textarea"),
]


def afinar_campos(campos: List[dict]) -> List[dict]:
    """Ajusta tipos por heurística y enlaza los campos '...con letra' con su
    importe para poder autocompletarlos."""
    ids = {c["id"] for c in campos}
    for c in campos:
        label = _sin_acentos((c.get("label") or c.get("id") or "")).lower()
        if c.get("tipo_input") not in TIPOS_INPUT:
            c["tipo_input"] = "text"
        for rx, tipo in _HINTS_TIPO:
            if re.search(rx, label):
                if not (tipo == "currency" and re.search(r"\b(con letra|en letra|letras)\b", label)):
                    c["tipo_input"] = tipo
                break
        c.setdefault("grupo", "Datos del contrato")
        c.setdefault("ayuda", "")
        c.setdefault("ejemplo", "")
        c.setdefault("ocurrencias", 1)
        c.setdefault("obligatorio", True)

    # Enlace importe -> importe con letra
    for c in campos:
        cid = c["id"]
        m = re.match(r"^(.*?)_(?:con_)?letras?$", cid)
        base = m.group(1) if m else None
        if not base:
            label = _sin_acentos((c.get("label") or "")).lower()
            if re.search(r"\b(con letra|en letra)\b", label):
                for otro in campos:
                    if otro["id"] == cid:
                        continue
                    if otro.get("tipo_input") == "currency" and \
                       _sin_acentos(otro.get("label") or "").lower() in label:
                        base = otro["id"]
                        break
        if base and base in ids and base != cid:
            c["auto_letras_de"] = base
            c["tipo_input"] = "text"
            if not c.get("ayuda"):
                c["ayuda"] = "Se llena solo con el importe; puedes editarlo."

    orden_grupo, vistos = [], set()
    for c in campos:
        g = c["grupo"]
        if g not in vistos:
            vistos.add(g)
            orden_grupo.append(g)
    campos.sort(key=lambda c: orden_grupo.index(c["grupo"]))
    return campos


# ────────────────────────────────────────────────────────────────
# NORMALIZACIÓN Y RELLENO
# ────────────────────────────────────────────────────────────────

def normalizar(doc, snap, spans: Dict[int, List[Tuple[int, int, str]]]) -> bytes:
    """Reescribe el DOCX con los marcadores {{id}} en su lugar."""
    for i, lista in spans.items():
        aplicar_spans(snap[i]["runs"], lista)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


_RE_PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]{1,60})\s*\}\}")


def _valor_vacio(cid: str, modo: str) -> Optional[str]:
    """Qué se escribe cuando el usuario dejó un campo sin llenar.
    'linea'    -> una raya para completar a mano (documento final)
    'marcador' -> se queda {{id}} tal cual (vista previa: se ve qué falta)
    'vacio'    -> se borra
    """
    if modo == "marcador":
        return None
    return "" if modo == "vacio" else "__________"


def rellenar(content: bytes, valores: Dict[str, str],
             campos: Optional[List[dict]] = None,
             modo_vacio: str = "linea") -> bytes:
    """Rellena una plantilla ya normalizada, respetando el formato original."""
    doc = cargar_docx(content)
    snap = snapshot(doc)

    vals = {k: ("" if v is None else str(v)) for k, v in (valores or {}).items()
            if not str(k).startswith("__")}
    vals = completar_letras(vals, campos or [])

    for s in snap:
        spans = []
        for m in _RE_PLACEHOLDER.finditer(s["texto"]):
            cid = m.group(1)
            v = (vals.get(cid) or "").strip()
            if not v:
                v = _valor_vacio(cid, modo_vacio)
                if v is None:
                    continue
            spans.append((m.start(), m.end(), v))
        if spans:
            aplicar_spans(s["runs"], spans)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def completar_letras(vals: Dict[str, str], campos: List[dict]) -> Dict[str, str]:
    """Si el usuario dejó vacío un campo 'con letra' y sí capturó el importe,
    lo escribimos por él."""
    vals = dict(vals)
    for c in campos or []:
        base = c.get("auto_letras_de")
        if not base:
            continue
        cid = c.get("id")
        if vals.get(cid, "").strip():
            continue
        origen = vals.get(base, "")
        if not str(origen).strip():
            continue
        letras = numero_a_letras(origen)
        if letras:
            vals[cid] = letras
    return vals


def campos_en_plantilla(content: bytes) -> List[str]:
    """Ids realmente presentes en la plantilla normalizada (para verificar)."""
    snap = snapshot(cargar_docx(content))
    ids, vistos = [], set()
    for s in snap:
        for m in _RE_PLACEHOLDER.finditer(s["texto"]):
            cid = m.group(1)
            if cid not in vistos:
                vistos.add(cid)
                ids.append(cid)
    return ids


def previsualizar(content: bytes, valores: Optional[Dict[str, str]] = None,
                  campos: Optional[List[dict]] = None,
                  max_parrafos: int = 400) -> List[Dict[str, Any]]:
    """Texto del contrato con los valores ya puestos. Los {{id}} que sobrevivan
    son justo los datos que al usuario le faltó capturar."""
    content = rellenar(content, valores or {}, campos, modo_vacio="marcador")
    snap = snapshot(cargar_docx(content))
    out = []
    for s in snap[:max_parrafos]:
        t = s["texto"]
        if not t.strip():
            continue
        out.append({"texto": t, "campos": _RE_PLACEHOLDER.findall(t)})
    return out


# ────────────────────────────────────────────────────────────────
# ORQUESTADOR
# ────────────────────────────────────────────────────────────────

async def analizar(content: bytes, tipo: str = "", api_key: str = "",
                   modelo: str = MODELO_DEFAULT) -> Dict[str, Any]:
    """Analiza un DOCX y devuelve la plantilla normalizada + los campos.

    {
      "campos": [...], "plantilla": bytes, "motor": "marcadores|blancos|ia",
      "texto_preview": str, "descartados": [...], "raws": [...]
    }
    """
    doc = cargar_docx(content)
    snap = snapshot(doc)
    texto = texto_completo(snap)
    if not texto.strip():
        raise ValueError("El documento no tiene texto legible. "
                         "Si lo escaneaste, súbelo como Word editable.")

    raws: List[dict] = []
    descartados: List[dict] = []

    marc = detectar_marcadores(snap)
    blancos = detectar_blancos(snap)

    if marc["campos"] or blancos["campos"]:
        campos = marc["campos"] + blancos["campos"]
        spans = dict(marc["spans"])
        for i, lista in blancos["spans"].items():
            spans.setdefault(i, []).extend(lista)
        motor = "mixto" if (marc["campos"] and blancos["campos"]) \
            else (marc["motor"] or blancos["motor"])
        plantilla = normalizar(doc, snap, spans)
        if api_key:
            try:
                texto_norm = texto_completo(snapshot(cargar_docx(plantilla)))
                campos, r = await etiquetar_con_ia(api_key, texto_norm, campos, tipo, modelo)
                raws += r
            except Exception as e:
                print(f"[machotes] etiquetado IA omitido: {e}")
    else:
        if not api_key:
            raise ValueError("No encontramos variables marcadas en tu machote y el "
                             "análisis con IA no está disponible en este momento.")
        candidatos, raws = await detectar_con_ia(api_key, texto, tipo, modelo)
        if not candidatos:
            raise ValueError("La IA no encontró datos variables en este documento. "
                             "Revisa que sea un contrato y no un instructivo.")
        campos, spans, descartados = anclar_literales(snap, candidatos)
        if not campos:
            raise ValueError("Detectamos variables pero no pudimos ubicarlas en el "
                             "archivo. Vuelve a intentarlo.")
        motor = "ia"
        plantilla = normalizar(doc, snap, spans)

    campos = afinar_campos(campos)

    # Verificación dura: solo sobreviven los campos que de verdad quedaron
    # escritos como {{id}} en la plantilla. Si algo no se ancló, no se muestra.
    presentes = set(campos_en_plantilla(plantilla))
    campos = [c for c in campos if c["id"] in presentes]
    if not campos:
        raise ValueError("No pudimos preparar la plantilla a partir de este archivo.")

    return {
        "campos": campos,
        "plantilla": plantilla,
        "motor": motor,
        "texto_preview": texto[:900],
        "descartados": descartados,
        "raws": raws,
    }
