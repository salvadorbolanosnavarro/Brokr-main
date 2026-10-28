"""Contratos de Broquer para Colombia, Perú, Argentina y Chile.

generar_contrato.py arma los contratos mexicanos. Cuando los datos traen
``pais`` distinto de MX, delega aquí: mismo formulario, mismas llaves de
``datos``, pero cada contrato cita la ley de su país y usa su vocabulario
(locador/locatario y boleto en Argentina, arras confirmatorias en Perú,
deudor solidario en Colombia, aval y codeudor solidario en Chile).

Son modelos de referencia: deben revisarlos abogados de cada país antes
del primer uso real. Ajustar una cláusula es editar PAISES de abajo.
"""
from __future__ import annotations

from typing import Callable, Dict, List

from generar_contrato import clausula, firma_line, heading, numero_a_letras, p, setup_doc

MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
         'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
ORDINALES = ['PRIMERA', 'SEGUNDA', 'TERCERA', 'CUARTA', 'QUINTA', 'SEXTA', 'SÉPTIMA',
             'OCTAVA', 'NOVENA', 'DÉCIMA', 'DÉCIMA PRIMERA', 'DÉCIMA SEGUNDA',
             'DÉCIMA TERCERA', 'DÉCIMA CUARTA', 'DÉCIMA QUINTA', 'DÉCIMA SEXTA',
             'DÉCIMA SÉPTIMA', 'DÉCIMA OCTAVA', 'DÉCIMA NOVENA', 'VIGÉSIMA']

# Cómo se escribe cada moneda en letras dentro del contrato.
MONEDAS = {
    'COP': ('PESOS COLOMBIANOS', '$', 'COP'),
    'PEN': ('SOLES', 'S/', 'PEN'),
    'ARS': ('PESOS ARGENTINOS', '$', 'ARS'),
    'CLP': ('PESOS CHILENOS', '$', 'CLP'),
    'UF': ('UNIDADES DE FOMENTO', 'UF', ''),
    'USD': ('DÓLARES DE LOS ESTADOS UNIDOS DE AMÉRICA', 'US$', 'USD'),
}

PAISES: Dict[str, dict] = {
    'CO': {
        'nombre': 'Colombia', 'moneda': 'COP',
        'arrendador': 'EL ARRENDADOR', 'arrendatario': 'EL ARRENDATARIO',
        'garante': 'EL DEUDOR SOLIDARIO', 'locacion': 'ARRENDAMIENTO',
        'titulo_arr': 'CONTRATO DE ARRENDAMIENTO DE INMUEBLE',
        'titulo_arr_vivienda': 'CONTRATO DE ARRENDAMIENTO DE VIVIENDA URBANA',
        'ley_arr': 'la Ley 820 de 2003 y, en lo no previsto, el Código Civil colombiano',
        'ley_arr_otro': 'el Código Civil y el Código de Comercio colombianos',
        'reajuste': ('el canon se reajustará cada doce (12) meses de ejecución del contrato en una proporción que '
                     'no excederá el ciento por ciento (100%) del incremento del índice de precios al consumidor '
                     '(IPC) del año calendario inmediatamente anterior, conforme al artículo 20 de la Ley 820 de 2003'),
        'tope_canon': ('Las partes declaran que el canon mensual no excede el uno por ciento (1%) del valor comercial '
                       'del inmueble, conforme al artículo 18 de la Ley 820 de 2003.'),
        'deposito_prohibido_vivienda': True,
        'prorroga': ('Vencido el plazo, el contrato se prorrogará automáticamente por un término igual al inicialmente '
                     'pactado, siempre que cada una de las partes haya cumplido sus obligaciones y el ARRENDATARIO se '
                     'avenga a los reajustes del canon, salvo que alguna de las partes dé aviso escrito de no '
                     'renovarlo con la anticipación que exige la ley.'),
        'impuestos': 'El impuesto predial del inmueble será a cargo del ARRENDADOR.',
        'restitucion': ('El incumplimiento de cualquiera de las obligaciones de este contrato, y en especial la falta '
                        'de pago del canon dentro del término pactado, faculta al ARRENDADOR para darlo por terminado y '
                        'exigir la restitución del inmueble por la vía del proceso de restitución de inmueble arrendado.'),
        'garante_txt': ('se constituye en DEUDOR SOLIDARIO del ARRENDATARIO respecto de todas las obligaciones de '
                        'este contrato y sus prórrogas, renunciando al beneficio de excusión, y acepta desde ahora '
                        'cualquier prórroga o reajuste sin necesidad de nueva notificación'),
        'jurisdiccion': 'los jueces de la República de Colombia del lugar de ubicación del inmueble',
        'titulo_pro': 'CONTRATO DE PROMESA DE COMPRAVENTA',
        'ley_pro': ('el artículo 89 de la Ley 153 de 1887 y los artículos 1611, 1857 y siguientes del Código Civil '
                    'colombiano'),
        'pro_requisito': ('Para dar cumplimiento al artículo 89 de la Ley 153 de 1887, las partes fijan la época en '
                          'que ha de celebrarse el contrato prometido: la escritura pública de compraventa se otorgará '
                          'en la notaría indicada en este contrato, a más tardar el {fecha_limite}, a las diez de la '
                          'mañana (10:00 a. m.).'),
        'arras': ('a título de arras confirmatorias, que se imputarán al precio. Sin perjuicio de la cláusula penal, '
                  'si el PROMITENTE COMPRADOR incumple perderá las arras, y si incumple el PROMITENTE VENDEDOR las '
                  'devolverá dobladas, conforme al artículo 1859 del Código Civil'),
        'vendedor': 'EL PROMITENTE VENDEDOR', 'comprador': 'EL PROMITENTE COMPRADOR',
        'registro': 'en el folio de matrícula inmobiliaria N.º {registro} de la Oficina de Registro de Instrumentos Públicos de {tomo}',
        'notaria': 'Notaría',
        'gastos_pro': ('Los gastos notariales se pagarán por partes iguales; la retención en la fuente a cargo del '
                       'PROMITENTE VENDEDOR y los impuestos y derechos de registro a cargo del PROMITENTE COMPRADOR.'),
    },
    'PE': {
        'nombre': 'Perú', 'moneda': 'PEN',
        'arrendador': 'EL ARRENDADOR', 'arrendatario': 'EL ARRENDATARIO',
        'garante': 'EL FIADOR SOLIDARIO', 'locacion': 'ARRENDAMIENTO',
        'titulo_arr': 'CONTRATO DE ARRENDAMIENTO DE INMUEBLE',
        'titulo_arr_vivienda': 'CONTRATO DE ARRENDAMIENTO DE INMUEBLE',
        'ley_arr': 'los artículos 1666 y siguientes del Código Civil peruano',
        'ley_arr_otro': 'los artículos 1666 y siguientes del Código Civil peruano',
        'reajuste': 'la renta se mantendrá durante el plazo pactado, salvo acuerdo escrito de las partes',
        'tope_canon': '',
        'deposito_prohibido_vivienda': False,
        'prorroga': ('El contrato no se renueva tácitamente. Si el ARRENDATARIO permanece en el inmueble después del '
                     'vencimiento, no se entenderá renovado: continuará bajo sus mismas estipulaciones hasta que el '
                     'ARRENDADOR solicite la devolución, conforme al artículo 1700 del Código Civil.'),
        'impuestos': ('El impuesto predial será a cargo del ARRENDADOR; los arbitrios municipales y los servicios, a '
                      'cargo del ARRENDATARIO.'),
        'restitucion': ('CLÁUSULA DE ALLANAMIENTO A FUTURO: el ARRENDATARIO se allana desde ahora a la demanda de '
                        'desalojo por conclusión del contrato o por falta de pago de la renta, conforme al artículo '
                        '594 del Código Procesal Civil, modificado por la Ley N.º 30201. La falta de pago de dos meses '
                        'y quince días faculta al ARRENDADOR a resolver el contrato.'),
        'garante_txt': ('se constituye en FIADOR SOLIDARIO del ARRENDATARIO por todas las obligaciones de este '
                        'contrato, con renuncia expresa al beneficio de excusión, conforme a los artículos 1868 y '
                        'siguientes del Código Civil'),
        'jurisdiccion': 'los jueces y tribunales del distrito judicial donde se ubica el inmueble',
        'titulo_pro': 'CONTRATO DE ARRAS CONFIRMATORIAS Y COMPROMISO DE COMPRAVENTA',
        'ley_pro': 'los artículos 1414 a 1425 y 1477 a 1479 del Código Civil peruano',
        'pro_requisito': ('Las partes se obligan a celebrar el contrato definitivo de compraventa y a firmar la minuta '
                          'y la escritura pública a más tardar el {fecha_limite}, plazo que no excede de un año '
                          'conforme al artículo 1416 del Código Civil.'),
        'arras': ('a título de arras confirmatorias, que forman parte del precio. Si el PROMITENTE COMPRADOR no '
                  'cumple, el PROMITENTE VENDEDOR podrá dejar sin efecto el contrato reteniendo las arras; si no '
                  'cumple el PROMITENTE VENDEDOR, deberá devolverlas dobladas, conforme al artículo 1478 del Código Civil'),
        'vendedor': 'EL PROMITENTE VENDEDOR', 'comprador': 'EL PROMITENTE COMPRADOR',
        'registro': 'en la Partida Electrónica N.º {registro} del Registro de Predios de la Zona Registral de {tomo}',
        'notaria': 'Notaría',
        'gastos_pro': ('Los gastos notariales y registrales serán de cargo del PROMITENTE COMPRADOR, quien además paga '
                       'el impuesto de alcabala; el impuesto a la renta que corresponda es de cargo del PROMITENTE VENDEDOR.'),
    },
    'AR': {
        'nombre': 'Argentina', 'moneda': 'USD',
        'arrendador': 'EL LOCADOR', 'arrendatario': 'EL LOCATARIO',
        'garante': 'EL FIADOR', 'locacion': 'LOCACIÓN',
        'titulo_arr': 'CONTRATO DE LOCACIÓN',
        'titulo_arr_vivienda': 'CONTRATO DE LOCACIÓN DE INMUEBLE CON DESTINO HABITACIONAL',
        'ley_arr': 'los artículos 1187 a 1226 del Código Civil y Comercial de la Nación',
        'ley_arr_otro': 'los artículos 1187 a 1226 del Código Civil y Comercial de la Nación',
        'reajuste': ('el precio se actualizará cada doce (12) meses según la variación del Índice de Precios al '
                     'Consumidor (IPC) publicado por el INDEC, salvo que la locación se haya pactado en moneda '
                     'extranjera, en cuyo caso no se actualiza'),
        'tope_canon': '',
        'deposito_prohibido_vivienda': False,
        'prorroga': ('Vencido el plazo, el LOCATARIO deberá restituir el inmueble. La continuación en la tenencia no '
                     'importa tácita reconducción, conforme al artículo 1218 del Código Civil y Comercial de la Nación.'),
        'impuestos': ('Los impuestos y tasas que gravan el inmueble son a cargo del LOCADOR; las expensas ordinarias y '
                      'los servicios, a cargo del LOCATARIO.'),
        'restitucion': ('El LOCATARIO podrá resolver anticipadamente el contrato en los términos del artículo 1221 del '
                        'Código Civil y Comercial de la Nación. La falta de pago de dos períodos consecutivos faculta '
                        'al LOCADOR a resolver el contrato y demandar el desalojo, previa intimación de pago.'),
        'garante_txt': ('se constituye en FIADOR, liso, llano y principal pagador de todas las obligaciones del '
                        'LOCATARIO hasta la restitución efectiva del inmueble, con renuncia a los beneficios de '
                        'excusión y división, conforme a los artículos 1584 y 1590 del Código Civil y Comercial'),
        'jurisdiccion': 'los tribunales ordinarios con competencia en el lugar de ubicación del inmueble',
        'titulo_pro': 'BOLETO DE COMPRAVENTA',
        'ley_pro': 'los artículos 1123, 1170, 1171 y concordantes del Código Civil y Comercial de la Nación',
        'pro_requisito': ('La escritura traslativa de dominio se otorgará ante el escribano que designe la parte '
                          'compradora, a más tardar el {fecha_limite}.'),
        'arras': ('en concepto de seña, a cuenta de precio y con carácter confirmatorio conforme a los artículos 1059 '
                  'y 1060 del Código Civil y Comercial de la Nación'),
        'vendedor': 'LA PARTE VENDEDORA', 'comprador': 'LA PARTE COMPRADORA',
        'registro': 'en la matrícula N.º {registro} del Registro de la Propiedad Inmueble de {tomo}',
        'notaria': 'Registro Notarial',
        'gastos_pro': ('Los honorarios de escribanía y los gastos de la escritura serán a cargo de la parte '
                       'compradora; los certificados, deudas de impuestos, tasas y expensas hasta la posesión, de '
                       'la parte vendedora. El impuesto de sellos se paga por mitades.'),
    },
    'CL': {
        'nombre': 'Chile', 'moneda': 'CLP',
        'arrendador': 'EL ARRENDADOR', 'arrendatario': 'EL ARRENDATARIO',
        'garante': 'EL AVAL Y CODEUDOR SOLIDARIO', 'locacion': 'ARRENDAMIENTO',
        'titulo_arr': 'CONTRATO DE ARRENDAMIENTO',
        'titulo_arr_vivienda': 'CONTRATO DE ARRENDAMIENTO DE INMUEBLE URBANO',
        'ley_arr': 'la Ley N.º 18.101 sobre arrendamiento de predios urbanos y los artículos 1915 y siguientes del Código Civil',
        'ley_arr_otro': 'la Ley N.º 18.101 y los artículos 1915 y siguientes del Código Civil',
        'reajuste': ('la renta se reajustará cada doce (12) meses según la variación del Índice de Precios al '
                     'Consumidor (IPC) informada por el INE; si se pactó en Unidades de Fomento, no se reajusta'),
        'tope_canon': '',
        'deposito_prohibido_vivienda': False,
        'prorroga': ('Si ninguna de las partes da aviso de término con al menos sesenta (60) días de anticipación al '
                     'vencimiento, el contrato se renovará por un período igual.'),
        'impuestos': ('Las contribuciones de bienes raíces son de cargo del ARRENDADOR; los gastos comunes y los '
                      'servicios, de cargo del ARRENDATARIO.'),
        'restitucion': ('La falta de pago de la renta faculta al ARRENDADOR a poner término al contrato y a demandar la '
                        'restitución del inmueble y el cobro de lo adeudado, incluso por el procedimiento monitorio '
                        'de la Ley N.º 21.461.'),
        'garante_txt': ('se constituye en AVAL Y CODEUDOR SOLIDARIO del ARRENDATARIO por todas las obligaciones de '
                        'este contrato y sus renovaciones'),
        'jurisdiccion': 'los tribunales ordinarios de justicia de la comuna donde se ubica el inmueble',
        'titulo_pro': 'CONTRATO DE PROMESA DE COMPRAVENTA',
        'ley_pro': 'el artículo 1554 del Código Civil chileno',
        'pro_requisito': ('Conforme al artículo 1554 del Código Civil, las partes fijan el plazo para celebrar el '
                          'contrato prometido: la escritura pública de compraventa se firmará a más tardar el '
                          '{fecha_limite}. Las partes firmarán este contrato ante notario.'),
        'arras': ('a título de arras, que se imputarán al precio, conforme a los artículos 1803 a 1805 del Código Civil'),
        'vendedor': 'EL PROMITENTE VENDEDOR', 'comprador': 'EL PROMITENTE COMPRADOR',
        'registro': 'a fojas {registro} del Registro de Propiedad del Conservador de Bienes Raíces de {tomo}',
        'notaria': 'Notaría',
        'gastos_pro': ('Los gastos notariales y del Conservador de Bienes Raíces serán de cargo del PROMITENTE '
                       'COMPRADOR, salvo los de alzamiento de hipotecas o gravámenes, que son del PROMITENTE VENDEDOR.'),
    },
}


def _fecha(v: str) -> str:
    v = (v or '').strip()
    if not v or ' de ' in v.lower():
        return v.lower()
    try:
        y, m, d = (int(x) for x in v[:10].split('-'))
        return f'{d} de {MESES[m - 1]} de {y}'
    except (ValueError, IndexError):
        return v


def _num(v) -> float:
    try:
        return float(str(v or 0).replace(',', '').replace('$', '').replace('US', '').strip() or 0)
    except ValueError:
        return 0.0


def monto(v, moneda: str, pais: str = 'CO') -> str:
    """$1.500.000,00 COP (UN MILLÓN QUINIENTOS MIL PESOS COLOMBIANOS)."""
    n = _num(v)
    nombre, simbolo, codigo = MONEDAS.get(moneda, MONEDAS['USD'])
    entero = int(n)
    dec = round((n - entero) * 100)
    numero = f'{n:,.2f}'
    if pais != 'PE':  # Colombia, Argentina y Chile: punto de miles y coma decimal.
        numero = numero.replace(',', '_').replace('.', ',').replace('_', '.')
    cifra = f'{simbolo} {numero}' if moneda == 'UF' else f'{simbolo}{numero}'
    if codigo:
        cifra += f' {codigo}'
    letras = numero_a_letras(entero) + f' {nombre}'
    if dec:
        letras += f' CON {dec:02d}/100'
    return f'{cifra} ({letras})'


class _Contrato:
    def __init__(self, datos: dict, pais: str):
        self.d = datos
        self.c = PAISES[pais]
        self.pais = pais
        self.moneda = (datos.get('moneda') or self.c['moneda']).upper()
        self.doc = setup_doc()
        self.n = 0

    def v(self, k: str, default: str = '') -> str:
        return str(self.d.get(k) or default).strip()

    def V(self, k: str, default: str = '') -> str:
        return self.v(k, default).upper()

    def clausula(self, titulo: str, texto: str) -> None:
        if not texto:
            return
        numero = ORDINALES[self.n] if self.n < len(ORDINALES) else str(self.n + 1)
        self.n += 1
        clausula(self.doc, numero, titulo, texto)

    def especiales(self) -> None:
        for txt in self.d.get('clausulas_especiales') or []:
            for parrafo in str(txt).split('\n'):
                if parrafo.strip():
                    p(self.doc, parrafo.strip())

    def firmas(self, pares: List[tuple]) -> None:
        p(self.doc, '')
        for etiqueta, nombre in pares:
            if nombre:
                firma_line(self.doc, etiqueta, nombre)

    def domicilio(self, clave: str, sufijo: str) -> str:
        dom = self.v(clave) or self.direccion(sufijo)
        return f', con domicilio en {dom}' if dom else ''

    def direccion(self, sufijo: str = 'inmueble') -> str:
        partes = [self.v(f'calle_{sufijo}'), self.v(f'num_ext_{sufijo}'),
                  self.v(f'num_int_{sufijo}') and 'Int. ' + self.v(f'num_int_{sufijo}'),
                  self.v(f'colonia_{sufijo}'), self.v(f'municipio_{sufijo}'), self.v(f'estado_{sufijo}')]
        return ', '.join(x for x in partes if x) or self.v(f'direccion_{sufijo}') or self.v(f'domicilio_{sufijo}')


def generar_arrendamiento(datos: dict, pais: str, salida: str) -> None:
    k = _Contrato(datos, pais)
    c, doc = k.c, k.doc
    destino = k.v('destino_uso') or 'casa habitación'
    vivienda = any(w in destino.lower() for w in ('habita', 'vivienda', 'casa', 'departamento', 'depa'))
    arr, arrt, gar = c['arrendador'], c['arrendatario'], c['garante']
    ciudad = k.v('ciudad_firma') or k.v('municipio_inmueble')
    nombre_arr, nombre_arrt, nombre_gar = k.V('nombre_arrendador'), k.V('nombre_arrendatario'), k.V('nombre_obligado_solidario')

    heading(doc, c['titulo_arr_vivienda'] if vivienda else c['titulo_arr'])
    comparecen = (f'En {ciudad}, {c["nombre"]}, a {_fecha(k.v("fecha_contrato"))}, celebran el presente contrato de '
                  f'{c["locacion"].lower()}, por una parte {nombre_arr}, en adelante "{arr}"'
                  f'{k.domicilio("domicilio_arrendador", "arrendador")}; y por la otra {nombre_arrt}, en adelante "{arrt}"')
    if nombre_gar:
        comparecen += f'; y {nombre_gar}, en adelante "{gar}"{k.domicilio("domicilio_obligado_solidario", "os")}'
    comparecen += (f', quienes se rigen por {c["ley_arr"] if vivienda else c["ley_arr_otro"]} y por las siguientes '
                   'cláusulas:')
    p(doc, comparecen)

    k.clausula('OBJETO', f'{arr} entrega a {arrt} el uso y goce del inmueble ubicado en {k.direccion()}, '
                         f'que este recibe en buen estado, para destinarlo exclusivamente a {destino.lower()}. '
                         f'{arrt} no podrá cambiar ese destino sin autorización escrita de {arr}.')
    plazo = k.v('plazo_contrato') or k.v('duracion')
    k.clausula('PLAZO', f'El plazo es de {plazo.lower() or "el que va de la fecha de inicio a la de término"}, del '
                        f'{_fecha(k.v("fecha_inicio"))} al {_fecha(k.v("fecha_fin"))}. {c["prorroga"]}')
    renta = (f'{arrt} pagará a {arr} una renta mensual de {monto(k.v("renta_mensual"), k.moneda, k.pais)}, por mes '
             f'anticipado, a más tardar el día {k.v("dia_pago", "5")} de cada mes')
    if k.v('forma_pago'):
        renta += f', mediante {k.v("forma_pago").lower()}'
    if k.v('cuenta_bancaria'):
        renta += f' a la cuenta {k.v("cuenta_bancaria")}'
    renta += f'. Durante el contrato {c["reajuste"]}.'
    if vivienda and c['tope_canon']:
        renta += ' ' + c['tope_canon']
    k.clausula('RENTA', renta)

    if vivienda and c['deposito_prohibido_vivienda']:
        k.clausula('GARANTÍAS', 'Conforme al artículo 16 de la Ley 820 de 2003, en el arrendamiento de vivienda '
                                'urbana no se exigen depósitos en dinero. El cumplimiento se garantiza con la '
                                f'solidaridad de {gar} y, si las partes lo acuerdan, con una póliza de seguro de '
                                'arrendamiento.')
    elif _num(k.v('deposito_garantia')):
        k.clausula('GARANTÍA', f'{arrt} entrega en este acto a {arr} la suma de {monto(k.v("deposito_garantia"), k.moneda, k.pais)} '
                               'en garantía del cumplimiento de sus obligaciones. No podrá imputarse al pago de rentas. '
                               f'{arr} la devolverá dentro de los treinta (30) días siguientes a la restitución del '
                               'inmueble, descontando las rentas, servicios y daños pendientes que se acrediten.')
    k.clausula('SERVICIOS Y GASTOS', f'Los servicios de energía, agua, gas, internet y demás que consuma el '
                                     f'inmueble serán a cargo de {arrt}. {c["impuestos"]}')
    k.clausula('CONSERVACIÓN Y REPARACIONES', f'{arrt} conservará el inmueble y hará las reparaciones locativas o '
                                             'menores que su uso requiera; las reparaciones necesarias o estructurales '
                                             f'son a cargo de {arr}, salvo que se deban a culpa de {arrt}. Toda mejora '
                                             f'requiere autorización escrita de {arr} y quedará en beneficio del inmueble.')
    k.clausula('PROHIBICIONES', f'{arrt} no podrá subarrendar, ceder el contrato ni transferir la tenencia total o '
                                f'parcial del inmueble sin consentimiento escrito de {arr}.')
    k.clausula('TERMINACIÓN Y RESTITUCIÓN', c['restitucion'])
    if _num(k.v('pena_dia_num')):
        k.clausula('PENALIDAD', f'Si {arrt} no restituye el inmueble al término del contrato, pagará a {arr} una '
                                f'penalidad de {monto(k.v("pena_dia_num"), k.moneda, k.pais)} por cada día de retraso, sin '
                                'perjuicio de la renta que se siga causando y de la acción de restitución.')
    if nombre_gar:
        k.clausula('GARANTE', f'{nombre_gar} {c["garante_txt"]}.')
    k.clausula('DOMICILIOS Y NOTIFICACIONES', 'Las partes señalan como domicilios los indicados en este contrato; '
                                             f'{arrt} señala el inmueble arrendado. Cualquier cambio deberá avisarse por escrito.')
    k.clausula('LEY APLICABLE Y JURISDICCIÓN', f'Este contrato se rige por las leyes de {c["nombre"]}. Para su '
                                              f'interpretación y cumplimiento, las partes se someten a {c["jurisdiccion"]}.')
    k.especiales()
    p(doc, f'Leído el presente contrato, las partes lo firman en señal de conformidad en {ciudad}, el '
           f'{_fecha(k.v("fecha_contrato"))}.')
    k.firmas([(arr, nombre_arr), (arrt, nombre_arrt), (gar, nombre_gar),
              ('TESTIGO', k.V('testigo_1')), ('TESTIGO', k.V('testigo_2'))])
    doc.save(salida)


def generar_promesa(datos: dict, pais: str, salida: str) -> None:
    k = _Contrato(datos, pais)
    c, doc = k.c, k.doc
    ven, com = c['vendedor'], c['comprador']
    ciudad = k.v('ciudad_firma') or k.v('municipio_inmueble')
    nombre_ven, nombre_com = k.V('nombre_vendedor'), k.V('nombre_comprador')

    heading(doc, c['titulo_pro'])
    p(doc, f'En {ciudad}, {c["nombre"]}, a {_fecha(k.v("fecha_contrato"))}, celebran el presente contrato, por una '
           f'parte {nombre_ven}, en adelante "{ven}"{k.domicilio("domicilio_vendedor", "vendedor")}; '
           f'y por la otra {nombre_com}, en adelante "{com}"{k.domicilio("domicilio_comprador", "comprador")}, '
           f'conforme {("al " + c["ley_pro"][3:]) if c["ley_pro"].startswith("el ") else "a " + c["ley_pro"]} '
           'y a las siguientes cláusulas:')

    titulo = ''
    if k.v('escritura_numero') or k.v('notario_numero'):
        titulo = (f', según título contenido en la escritura pública N.º {k.v("escritura_numero") or "____"} otorgada '
                  f'ante {k.v("notario_nombre") or "el notario"}{", " + c["notaria"] + " N.º " + k.v("notario_numero") if k.v("notario_numero") else ""}'
                  f'{" de " + k.v("estado_notaria") if k.v("estado_notaria") else ""}')
    registro = ''
    if k.v('registro') or k.v('tomo_registro'):
        registro = ', inscrito ' + c['registro'].format(registro=k.v('registro') or '____',
                                                              tomo=k.v('tomo_registro') or '____')
    k.clausula('ANTECEDENTES', f'{ven} declara ser titular del dominio del inmueble ubicado en {k.direccion()}{titulo}{registro}, '
                               'y que está libre de gravámenes, embargos, limitaciones al dominio y adeudos de impuestos, '
                               'servicios y cuotas de administración, o que los cancelará antes de la escritura.')
    k.clausula('OBJETO', f'{ven} promete vender y {com} promete comprar el inmueble descrito, con todos sus usos, '
                         'costumbres, servidumbres y lo que de hecho y por derecho le corresponde.')
    k.clausula('PRECIO', f'El precio total es de {monto(k.v("precio_total"), k.moneda, k.pais)}.')
    pago = f'En este acto {com} entrega a {ven} la suma de {monto(k.v("monto_arras"), k.moneda, k.pais)}, {c["arras"]}. '
    pago += f'El saldo de {monto(k.v("monto_saldo"), k.moneda, k.pais)} se pagará al firmarse la escritura pública'
    if k.v('forma_pago_saldo'):
        pago += f', mediante {k.v("forma_pago_saldo").lower()}'
    if k.v('cuenta_vendedor'):
        pago += f', a la cuenta {k.v("cuenta_vendedor")}{" del banco " + k.v("banco_vendedor") if k.v("banco_vendedor") else ""}'
    k.clausula('FORMA DE PAGO', pago + '.')
    k.clausula('ESCRITURA', c['pro_requisito'].format(fecha_limite=_fecha(k.v('fecha_limite_escritura')) or '____'))
    k.clausula('ENTREGA', f'{ven} entregará el inmueble a {com} a la firma de la escritura pública, desocupado, a paz y '
                          'salvo por servicios e impuestos, y en el estado en que se encuentra hoy.')
    k.clausula('GASTOS E IMPUESTOS', c['gastos_pro'])
    if _num(k.v('pena_convencional')):
        k.clausula('CLÁUSULA PENAL', f'La parte que incumpla pagará a la otra, a título de pena, la suma de '
                                     f'{monto(k.v("pena_convencional"), k.moneda, k.pais)}, sin perjuicio de que la parte '
                                     'cumplida pueda exigir el cumplimiento del contrato.')
    k.clausula('LEY APLICABLE Y JURISDICCIÓN', f'Este contrato se rige por las leyes de {c["nombre"]}. Para su '
                                              f'interpretación y cumplimiento, las partes se someten a {c["jurisdiccion"]}.')
    k.especiales()
    p(doc, f'Leído el presente contrato, las partes lo firman en señal de conformidad en {ciudad}, el '
           f'{_fecha(k.v("fecha_contrato"))}.')
    k.firmas([(ven, nombre_ven), (com, nombre_com),
              ('TESTIGO', k.V('testigo_1')), ('TESTIGO', k.V('testigo_2'))])
    doc.save(salida)


GENERADORES: Dict[str, Callable[[dict, str, str], None]] = {
    'arrendamiento': generar_arrendamiento,
    'promesa': generar_promesa,
}


def generar(tipo: str, datos: dict, salida: str) -> None:
    pais = str(datos.get('pais') or '').upper()
    if pais not in PAISES:
        raise ValueError(f'País sin contratos propios: {pais}')
    if tipo not in GENERADORES:
        raise ValueError(f'Tipo de contrato desconocido: {tipo}')
    GENERADORES[tipo](datos, pais, salida)

