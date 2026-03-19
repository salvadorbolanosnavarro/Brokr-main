#!/usr/bin/env python3
"""
Brokr Contract Generator
Generates DOCX contracts from JSON data
Usage: python3 generar_contrato.py <tipo> <datos.json> <output.docx>
"""

import sys
import json
import re
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import datetime

def numero_a_letras(n):
    """Convert number to Spanish words for legal contracts"""
    unidades = ['','UNO','DOS','TRES','CUATRO','CINCO','SEIS','SIETE','OCHO','NUEVE',
                'DIEZ','ONCE','DOCE','TRECE','CATORCE','QUINCE','DIECISÉIS',
                'DIECISIETE','DIECIOCHO','DIECINUEVE']
    decenas = ['','DIEZ','VEINTE','TREINTA','CUARENTA','CINCUENTA',
               'SESENTA','SETENTA','OCHENTA','NOVENTA']
    centenas = ['','CIENTO','DOSCIENTOS','TRESCIENTOS','CUATROCIENTOS','QUINIENTOS',
                'SEISCIENTOS','SETECIENTOS','OCHOCIENTOS','NOVECIENTOS']

    def convertir_grupo(n):
        if n == 0: return ''
        if n == 100: return 'CIEN'
        if n < 20: return unidades[n]
        if n < 100:
            d, u = divmod(n, 10)
            return decenas[d] + (' Y ' + unidades[u] if u else '')
        c, r = divmod(n, 100)
        return centenas[c] + (' ' + convertir_grupo(r) if r else '')

    n = int(n)
    if n == 0: return 'CERO'
    if n < 0: return 'MENOS ' + numero_a_letras(-n)

    partes = []
    if n >= 1000000:
        m, r = divmod(n, 1000000)
        partes.append(('UN MILLÓN' if m == 1 else convertir_grupo(m) + ' MILLONES'))
        n = r
    if n >= 1000:
        m, r = divmod(n, 1000)
        partes.append(('MIL' if m == 1 else convertir_grupo(m) + ' MIL'))
        n = r
    if n > 0:
        partes.append(convertir_grupo(n))

    return ' '.join(p for p in partes if p)

def fmt_monto(cantidad_str):
    """Format amount and return (formatted_number, words)"""
    try:
        # Strip currency symbols and commas
        clean = re.sub(r'[,$\s]', '', str(cantidad_str))
        n = float(clean)
        entero = int(n)
        cents = round((n - entero) * 100)
        formatted = f"${entero:,.2f}"
        words = numero_a_letras(entero)
        if cents > 0:
            words += f" PESOS {cents:02d}/100 M.N."
        else:
            words += " PESOS 00/100 M.N."
        return formatted, words
    except:
        return cantidad_str, cantidad_str

def setup_doc():
    doc = Document()
    # Page margins
    for section in doc.sections:
        section.top_margin    = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin   = Cm(3)
        section.right_margin  = Cm(3)

    # Default style
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(10)
    style.paragraph_format.space_after = Pt(6)

    return doc

def p(doc, text, bold=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
      size=10, space_before=0, space_after=6, indent=False):
    para = doc.add_paragraph()
    para.alignment = align
    para.paragraph_format.space_before = Pt(space_before)
    para.paragraph_format.space_after  = Pt(space_after)
    if indent:
        para.paragraph_format.left_indent = Cm(1)
    run = para.add_run(text)
    run.bold = run.bold or bold
    run.font.name = 'Arial'
    run.font.size = Pt(size)
    return para

def heading(doc, text, level=1):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_before = Pt(6)
    para.paragraph_format.space_after  = Pt(6)
    run = para.add_run(text)
    run.bold = True
    run.font.name = 'Arial'
    run.font.size = Pt(11 if level == 1 else 10)
    return para

def clausula(doc, numero, titulo, texto):
    """Add a clause with title and body"""
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    para.paragraph_format.space_before = Pt(8)
    para.paragraph_format.space_after  = Pt(4)
    r = para.add_run(f'"{titulo}"')
    r.bold = True
    r.font.name = 'Arial'
    r.font.size = Pt(10)

    body = doc.add_paragraph()
    body.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    body.paragraph_format.space_before = Pt(0)
    body.paragraph_format.space_after  = Pt(6)
    body.paragraph_format.left_indent  = Cm(0.5)
    r2 = body.add_run(f'{numero}- {texto}')
    r2.font.name = 'Arial'
    r2.font.size = Pt(10)
    return body

def firma_line(doc, label, nombre):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_before = Pt(30)
    para.paragraph_format.space_after  = Pt(2)
    r = para.add_run('_' * 35)
    r.font.name = 'Arial'
    r.font.size = Pt(10)

    para2 = doc.add_paragraph()
    para2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para2.paragraph_format.space_before = Pt(0)
    para2.paragraph_format.space_after  = Pt(2)
    r2 = para2.add_run(label)
    r2.bold = True
    r2.font.name = 'Arial'
    r2.font.size = Pt(10)

    para3 = doc.add_paragraph()
    para3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para3.paragraph_format.space_before = Pt(0)
    para3.paragraph_format.space_after  = Pt(20)
    r3 = para3.add_run(nombre.upper())
    r3.font.name = 'Arial'
    r3.font.size = Pt(10)

# ─────────────────────────────────────────────
# CONTRATO DE ARRENDAMIENTO
# ─────────────────────────────────────────────
def generar_arrendamiento(d, output_path):
    doc = setup_doc()

    # Format amounts
    renta_num, renta_letra   = fmt_monto(d['renta_mensual'])
    deposito_num, dep_letra  = fmt_monto(d['deposito_garantia'])
    _, pen_letra             = fmt_monto(d.get('pena_retencion', 500))
    pen_dia                  = d.get('pena_retencion', 500)

    fecha        = d['fecha_contrato']
    nombre_arr   = d['nombre_arrendador'].upper()
    nombre_arrta = d['nombre_arrendatario'].upper()
    nombre_os    = d['nombre_obligado_solidario'].upper()
    dir_inmueble = d['direccion_inmueble'].upper()
    cp_inmueble  = d['cp_inmueble']
    col_inmueble = d['colonia_inmueble'].upper()
    dom_arr      = d['domicilio_arrendador'].upper()
    dom_os       = d['domicilio_obligado_solidario'].upper()
    inm_os       = d['inmueble_os'].upper()  # inmueble que garantiza al OS
    destino      = d.get('destino_inmueble', 'CASA HABITACIÓN').upper()
    duracion     = d.get('duracion', 'UN AÑO')
    fecha_inicio = d['fecha_inicio']
    fecha_fin    = d['fecha_fin']
    dia_pago     = d.get('dia_pago', '1')
    forma_pago   = d.get('forma_pago', 'efectivo').lower()
    tiene_estac  = d.get('cajones_estacionamiento', 0)
    tiene_bodega = d.get('incluye_bodega', False)
    accesorios   = []
    if tiene_estac: accesorios.append(f"{tiene_estac} cajón(es) de estacionamiento")
    if tiene_bodega: accesorios.append("bodega")
    accesorios_txt = " y ".join(accesorios) if accesorios else ""

    # ── ENCABEZADO ──
    heading(doc, fecha.upper())
    doc.add_paragraph()

    p(doc,
      f"CONTRATO DE ARRENDAMIENTO QUE CELEBRAN POR UNA PARTE {nombre_arr}, "
      f"PROPIETARIO DEL INMUEBLE UBICADO EN {dir_inmueble}, COLONIA {col_inmueble}, "
      f"CÓDIGO POSTAL {cp_inmueble}, DE ESTA CIUDAD DE MORELIA, MICHOACÁN DE OCAMPO, "
      f"A QUIEN EN LO SUCESIVO SE LE DENOMINARÁ \"LA PARTE ARRENDADORA\", "
      f"Y POR LA OTRA PARTE {nombre_arrta}, "
      f"A QUIEN EN LO SUCESIVO SE LE DENOMINARÁ \"LA PARTE ARRENDATARIA\", "
      f"Y {nombre_os}, A QUIEN EN LO SUCESIVO SE LE DENOMINARÁ \"EL OBLIGADO SOLIDARIO\", "
      f"SUJETÁNDOSE LAS PARTES A LAS SIGUIENTES DECLARACIONES Y CLÁUSULAS:",
      bold=True)

    # ── DECLARACIONES ──
    heading(doc, "D E C L A R A C I O N E S :")

    p(doc, "1.- DECLARA LA PARTE ARRENDADORA BAJO PROTESTA DE DECIR VERDAD:", bold=True)
    p(doc,
      "1. SER MEXICANO(A), MAYOR DE EDAD, ASÍ COMO TENER EL CARÁCTER Y CAPACIDAD LEGAL "
      "PARA OBLIGARSE EN LOS TÉRMINOS DEL PRESENTE INSTRUMENTO, QUIEN SE IDENTIFICA "
      "PERSONALMENTE PARA LA FIRMA DEL PRESENTE INSTRUMENTO MEDIANTE CREDENCIAL DE ELECTOR; "
      "EMITIDA POR EL INSTITUTO NACIONAL ELECTORAL, QUE EN ORIGINAL EXHIBE, Y LA CUAL SE "
      "ANEXA AL PRESENTE INSTRUMENTO EN COPIA SIMPLE.", indent=True)
    p(doc,
      f"ASÍ MISMO DECLARA TENER LA VOLUNTAD DE DAR EN ARRENDAMIENTO EL INMUEBLE OBJETO DE "
      f"ESTE CONTRATO DE ARRENDAMIENTO, UBICADO EN {dir_inmueble}, COLONIA {col_inmueble}, "
      f"CÓDIGO POSTAL {cp_inmueble}, DE ESTA CIUDAD DE MORELIA, MICHOACÁN DE OCAMPO; "
      f"MISMO QUE NO PRESENTA NI SUFRE VICIOS OCULTOS O DEFECTOS Y POR LO TANTO SE ENCUENTRA "
      f"EN PERFECTAS CONDICIONES DE USO Y CONSERVACIÓN PARA SER UTILIZADO COMO {destino}.", indent=True)
    p(doc,
      f"2. TENER SU DOMICILIO PARA OIR Y RECIBIR TODO TIPO DE NOTIFICACIONES, DE CARÁCTER LEGAL, "
      f"ADMINISTRATIVO, FISCAL ETC., DERIVADOS DEL PRESENTE ACUERDO DE VOLUNTADES EL UBICADO EN "
      f"{dom_arr}, DE ESTA CIUDAD DE MORELIA, MICHOACÁN DE OCAMPO.", indent=True)

    p(doc, "2.- DECLARA LA PARTE ARRENDATARIA BAJO PROTESTA DE DECIR VERDAD:", bold=True)
    p(doc,
      "1. SER MEXICANO(A), MAYOR DE EDAD, ASÍ COMO TENER EL CARÁCTER, LA VOLUNTAD Y CAPACIDAD "
      "LEGAL PARA OBLIGARSE EN LOS TÉRMINOS DEL PRESENTE INSTRUMENTO; Y QUIEN SE IDENTIFICA "
      "PERSONALMENTE PARA LA FIRMA DEL PRESENTE CONTRATO MEDIANTE CREDENCIAL PARA VOTAR, QUE "
      "EN ORIGINAL EXHIBE, Y LA CUAL SE ANEXA AL PRESENTE INSTRUMENTO EN COPIA SIMPLE.", indent=True)
    p(doc,
      f"2. QUE HA CONSTATADO PERSONALMENTE LAS CONDICIONES FÍSICAS Y MATERIALES Y JURÍDICAS "
      f"DEL INMUEBLE EN LAS CUALES SE ENCUENTRA EL INMUEBLE OBJETO DEL PRESENTE CONTRATO, "
      f"LAS CUALES ENCUENTRA A SU ENTERA SATISFACCIÓN, MISMO QUE DESEA RECIBIR EN ARRENDAMIENTO "
      f"A CAMBIO DEL PAGO DE LA RENTA QUE SE ESTIPULA.", indent=True)
    p(doc,
      f"3. TENER Y SEÑALAR EN ESTE ACTO SU DOMICILIO PARA OIR Y RECIBIR TODO TIPO DE "
      f"NOTIFICACIONES PERSONALES DE CARÁCTER LEGAL, ADMINISTRATIVO, FISCALES, ETC., PARA LOS "
      f"EFECTOS DERIVADOS DEL PRESENTE INSTRUMENTO EL UBICADO EN {dir_inmueble}, COLONIA "
      f"{col_inmueble}, CÓDIGO POSTAL {cp_inmueble}, DE ESTA CIUDAD DE MORELIA, MICHOACÁN DE OCAMPO.", indent=True)

    p(doc, "3.- DECLARA EL OBLIGADO SOLIDARIO BAJO PROTESTA DE DECIR VERDAD:", bold=True)
    p(doc,
      f"3.1.- SER MEXICANO(A), MAYOR DE EDAD, ASÍ COMO TENER EL CARÁCTER, LA VOLUNTAD Y "
      f"CAPACIDAD LEGAL PARA OBLIGARSE EN LOS TÉRMINOS DEL PRESENTE INSTRUMENTO, CON SOLVENCIA "
      f"MORAL Y ECONÓMICA PARA DAR CUMPLIMIENTO AL MISMO EN SU CARÁCTER DE OBLIGADO SOLIDARIO, "
      f"ADEMÁS DE SER EN ESTE MOMENTO PROPIETARIO DEL INMUEBLE UBICADO EN {inm_os}, "
      f"MISMA PROPIEDAD QUE GARANTIZA SU SOLVENCIA ECONÓMICA PARA OBLIGARSE EN LOS TÉRMINOS DE "
      f"ESTE CONTRATO; QUIEN SE IDENTIFICA A LA FIRMA DEL PRESENTE CONTRATO MEDIANTE CREDENCIAL "
      f"PARA VOTAR, QUE EN ORIGINAL EXHIBE, Y LA CUAL SE ANEXA AL PRESENTE INSTRUMENTO EN COPIA SIMPLE.", indent=True)
    p(doc,
      f"3.2.- TENER Y SEÑALAR SU DOMICILIO PARA OIR Y RECIBIR TODO TIPO DE NOTIFICACIONES "
      f"PERSONALES DE CARÁCTER LEGAL, ADMINISTRATIVO, FISCALES, ETC., PARA LOS EFECTOS "
      f"DERIVADOS DEL PRESENTE INSTRUMENTO, EL UBICADO EN {dom_os}, DE ESTA CIUDAD DE "
      f"MORELIA, MICHOACÁN DE OCAMPO.", indent=True)

    p(doc,
      "Obligándose las partes a informar por escrito con anticipación cualquier cambio de "
      "domicilio y en caso de no hacerlo acuerdan que surtirá efecto legal cualquier "
      "comunicación, notificación, diligencia etc. que se les haga en los domicilios señalados.")

    heading(doc, "LAS PARTES DECLARAN QUE ES SU VOLUNTAD OBLIGARSE RECÍPROCAMENTE EN ESTE ACTO AL TENOR DE LAS SIGUIENTES:")
    heading(doc, "C L Á U S U L A S :")

    # ── CLÁUSULAS ──
    extra_acc = f" Incluyendo {accesorios_txt}." if accesorios_txt else ""
    clausula(doc, "PRIMERA.-", "OBJETO",
        f"La parte arrendadora, en este acto, entrega en arrendamiento a la parte arrendataria "
        f"y esta recibe de conformidad, a su entera satisfacción y bajo ese título el inmueble "
        f"descrito en la declaración 1. En buen estado físico de conservación para servir al "
        f"uso convenido.{extra_acc} No reservándose la parte arrendataria derecho alguno que "
        f"hacer valer ni en lo presente ni en lo futuro por este caso a la parte arrendadora.")

    clausula(doc, "SEGUNDA.-", "TÉRMINO CONTRATO",
        f"El término del contrato de arrendamiento es por {duracion.upper()}, obligatorio para "
        f"ambas partes. Debiendo acordar por escrito un nuevo término en caso de querer continuar "
        f"con el arrendamiento. Iniciando el término antes citado el {fecha_inicio} y finalizando "
        f"el {fecha_fin}. Con derecho de prórroga siempre y cuando la parte arrendataria se encuentre "
        f"al corriente del pago de las rentas y servicios. Debiendo la parte arrendataria dar aviso "
        f"en un plazo no mayor a 30 días antes de la fecha de vencimiento del presente instrumento, "
        f"su deseo de continuar con el arrendamiento, para que pueda ser valorado si existen las "
        f"condiciones para que sea renovado.")

    clausula(doc, "TERCERA.-", "PENALIZACIÓN",
        f"Acuerdan las partes que en caso de que la parte arrendataria no cumpla con el término de "
        f"{duracion.upper()}, o incurra en una de las causas de rescisión del presente instrumento, "
        f"deberá pagarle a la parte arrendadora, una penalización equivalente a un mes de renta. "
        f"Independientemente de los meses de renta vencidos a la fecha que esto suceda.")

    cuenta_bancaria = d.get('cuenta_bancaria', '').strip()
    banco_txt = (f" Los pagos deberán realizarse a la siguiente cuenta bancaria: {cuenta_bancaria}."
                 if cuenta_bancaria else "")

    clausula(doc, "CUARTA.-", "PRECIO RENTA",
        f"La parte arrendataria se obliga a pagarle puntualmente, sin requerimiento previo alguno, "
        f"a la parte arrendadora el importe de la renta del inmueble objeto del presente instrumento, "
        f"por la cantidad de: {renta_num} ({renta_letra}) por mes a transcurrir, en esta ciudad de "
        f"Morelia, Michoacán de Ocampo, mediante {forma_pago}.{banco_txt} Pagaderos a más tardar los días "
        f"{dia_pago} de cada mes. Obligándose la parte arrendataria a mantener al corriente los pagos "
        f"de agua, luz e internet, así como cualquier otro adeudo que se derive de la ocupación del "
        f"inmueble objeto de este contrato.\n\n"
        f"Acuerdan ambas partes que el importe del pago de la renta del inmueble aumentará cada año "
        f"sin previo aviso a la parte arrendataria, de acuerdo al Índice Nacional de Precios al "
        f"Consumidor, es decir que ese incremento entrará en vigor el día {fecha_inicio.split(' de ')[-1] if ' de ' in fecha_inicio else fecha_inicio} "
        f"del año siguiente y así sucesivamente.")

    clausula(doc, "QUINTA.-", "FORMA DE PAGO",
        f"La parte arrendataria se obliga con la parte arrendadora a cumplir puntualmente con el "
        f"pago de las rentas mensuales, así como cualquier otra prestación que se derive del presente "
        f"instrumento, en esta ciudad de Morelia, Michoacán. Los pagos de la renta deberán realizarse "
        f"en moneda nacional.\n\n"
        f"En caso de incumplimiento en el pago puntual de las rentas o de alguna otra prestación "
        f"inherente a este instrumento, ocasionará en perjuicio de la parte arrendataria la obligación "
        f"de pagar a la parte arrendadora el 10% DIEZ POR CIENTO MENSUAL de interés moratorio respecto "
        f"del importe de la renta que se encuentre vigente en ese momento, desde la constitución en mora "
        f"y hasta la total liquidación de todas y cada una de las obligaciones contraídas.")

    clausula(doc, "SEXTA.-", "DESTINO, OBJETO",
        f"La parte arrendataria deberá destinar únicamente el inmueble arrendado exclusivamente para "
        f"fines y objeto de {destino.lower()} en el caso de variar el fin y objeto será motivo de "
        f"rescisión SIN PREVIO AVISO del presente contrato de arrendamiento.")

    clausula(doc, "SÉPTIMA.-", "RESTRICCIONES",
        "La parte arrendataria no podrá realizar en el inmueble arrendado modificaciones ni obras "
        "sin el consentimiento por escrito del arrendador. En caso de ser autorizadas, dichas obras "
        "serán hechas a costa de la parte arrendataria y sin que tenga derecho a compensación o "
        "remuneración alguna, quedando dicha obra en beneficio del inmueble al terminar el arrendamiento.")

    clausula(doc, "OCTAVA.-", "RESCISIÓN",
        "El incumplimiento de cualquiera de las obligaciones contraídas por la parte arrendataria "
        "en este contrato, la falta de pago de una o más rentas vencidas, será causa de rescisión "
        "del mismo, bastando tan sólo que la parte arrendadora notifique por escrito a la parte "
        "arrendataria con una semana de anticipación su deseo de dar por rescindido el contrato, "
        "precisando la razón o motivo de esta causal.\n\n"
        f"Si la parte arrendataria desea rescindirlo después de {duracion.upper()} se avisará a "
        f"la parte arrendadora con 30 días de anticipación y sin penalización alguna.")

    clausula(doc, "NOVENA.-", "SUBARRENDAMIENTO",
        "La parte arrendataria NO podrá subarrendar en parte el inmueble arrendado y no podrá ceder "
        "ni traspasar en forma alguna los derechos y obligaciones adquiridos en este contrato, sin "
        "previo consentimiento dado por escrito por la parte arrendadora. En caso de que la parte "
        "arrendataria haga caso omiso a esta restricción contractual, será motivo de rescisión.")

    clausula(doc, "DÉCIMA.-", "SUSTANCIAS PELIGROSAS",
        "Expresamente se estipula que la parte arrendataria no podrá almacenar sustancias peligrosas, "
        "corrosivas, deletéreas o inflamables en el inmueble arrendado que puedan producir incendio u "
        "explosión. En caso de producirse siniestro en el inmueble arrendado por contravenir lo "
        "dispuesto en esta cláusula, la parte arrendataria deberá cubrir a la parte arrendadora todos "
        "los daños y perjuicios que le ocasione.")

    clausula(doc, "DECIMOPRIMERA.-", "RESPONSABILIDADES",
        "La parte arrendadora no será responsable de la seguridad de los bienes muebles que introduzca "
        "la parte arrendataria al inmueble arrendado. La parte arrendataria asume de manera enunciativa "
        "más no limitativa, toda la responsabilidad civil, laboral, penal, fiscal o de cualquier otra "
        "naturaleza, eximiendo a la parte arrendadora de todo género de responsabilidad derivada de sus "
        "actividades y de la ocupación del inmueble.")

    clausula(doc, "DECIMOSEGUNDA.-", "SINIESTROS",
        "En caso de que el inmueble arrendado sufriese daños por cualquier situación o fuera destruido "
        "total o parcialmente por incendio, terremoto o cualquier otro siniestro, la parte arrendadora "
        "no tendrá la obligación de efectuar cambios, reparaciones, mejoras o restaurar el inmueble "
        "objeto de este contrato, dándose por esta causa por terminado el presente contrato.")

    clausula(doc, "DECIMOTERCERA.-", "PREVENCIÓN",
        "Acuerdan las partes que la parte arrendadora por ningún motivo podrá ingresar al inmueble "
        "objeto de este contrato sino, hasta que sea entregado por la rescisión o terminación del "
        "presente instrumento. La parte arrendataria manifiesta que los recursos que destina al pago "
        "de la renta provienen de actividades lícitas, en cumplimiento a la Ley Federal para la "
        "Prevención e Identificación de Operaciones con Recursos de Procedencia Ilícita.")

    clausula(doc, "DECIMOCUARTA.-", "DEVOLUCIÓN DEL INMUEBLE",
        "Independientemente de la causa de rescisión del contrato o por su terminación, la parte "
        "arrendataria queda obligada a hacer la devolución del inmueble, de manera personal, "
        "entregándolo en buen estado de conservación y funcionamiento en que le fue entregado.")

    clausula(doc, "DECIMOQUINTA.-", "SERVICIOS",
        f"La parte arrendataria se obliga a entregar el inmueble al corriente de los pagos en los "
        f"servicios de agua, luz, gas, internet o cualquier otro servicio que derive de la ocupación "
        f"del inmueble. Para el caso en que al término de la vigencia forzosa del presente instrumento "
        f"no se elabore un nuevo contrato de arrendamiento, la parte arrendataria deberá entregar el "
        f"inmueble personalmente y totalmente desocupado a la parte arrendadora, a más tardar el día "
        f"{fecha_fin}. Por lo que si no lo hace, se obliga a pagar la cantidad de ${pen_dia:,.2f} "
        f"({pen_letra}) diarios, hasta que la desocupe y entregue, como pena convencional.")

    clausula(doc, "DECIMOSEXTA.-", "DEPÓSITO",
        f"La parte arrendataria entregará a la parte arrendadora, la cantidad de {deposito_num} "
        f"({dep_letra}), por concepto de DEPÓSITO EN GARANTÍA, sin que el mismo genere intereses "
        f"y sin que pueda ser aplicado a ninguna mensualidad por concepto de renta para garantizar "
        f"las obligaciones a su cargo emanadas del presente contrato. La cantidad depositada será "
        f"devuelta a los 30 (treinta) días después de finalizar el contrato de arrendamiento siempre "
        f"y cuando se haya cumplido la totalidad de las obligaciones de renta y de entrega del inmueble.")

    clausula(doc, "DECIMOSÉPTIMA.-", "APLICACIÓN DE PAGOS",
        "Cualquier pago que efectúe LA PARTE ARRENDATARIA a favor de LA PARTE ARRENDADORA se "
        "aplicará, primeramente, a cubrir los gastos que erogue LA PARTE ARRENDADORA y que "
        "correspondan a LA PARTE ARRENDATARIA en los términos del presente contrato, después "
        "serán imputados al pago de los intereses moratorios, y por último, al pago de las "
        "rentas generadas y no cubiertas.")

    clausula(doc, "DECIMOCTAVA.-", "DERECHO DEL TANTO",
        "La parte arrendataria renuncia expresamente al derecho de preferencia o derecho del tanto, "
        "es decir, para la compra del inmueble.")

    clausula(doc, "DECIMONOVENA.-", "TRANSMISIÓN DE LA PROPIEDAD",
        "Si durante la vigencia del contrato de arrendamiento se verificare la transmisión de la "
        "propiedad inmueble arrendado, el arrendamiento subsistirá en los mismos términos que "
        "establece el presente contrato.")

    clausula(doc, "VIGÉSIMA.-", "OBLIGADO SOLIDARIO",
        f"El obligado solidario se constituye como responsable de todas y cada una de las obligaciones "
        f"contraídas por la parte arrendataria, haciendo todas las renuncias que la parte arrendataria "
        f"tiene hechas, y los beneficios que de orden y exclusión consignadas en el Código Civil del "
        f"estado de Michoacán de Ocampo, no cesando la responsabilidad de este sino hasta cuando la "
        f"parte arrendadora se dé por recibido de la totalidad de todo cuanto se le deba.")

    clausula(doc, "VIGESIMOPRIMERA.-", "CONFIDENCIALIDAD",
        "Las partes se obligan a mantener de forma confidencial toda la información y documentación "
        "relativa al presente instrumento y a la operación que prometen llevar a cabo, a no divulgar "
        "a terceros sin el consentimiento previo y por escrito de cualquiera de ellas.")

    clausula(doc, "VIGESIMOSEGUNDA.-", "COMPETENCIA LEGAL",
        "Para todas las cuestiones relativas al alcance de la interpretación y cumplimiento de las "
        "obligaciones y derechos que se consignan en este contrato, las partes contratantes se someten "
        "expresamente a las leyes y a los tribunales competentes en la ciudad de Morelia, Michoacán de "
        "Ocampo, renunciando al fuero que por sus domicilios actuales o futuros pudiera corresponderles. "
        "Conviniendo que serán a cargo de la parte arrendataria, todos los gastos y costas judiciales "
        "y extrajudiciales a que dieran lugar por incumplimiento del contrato en caso de controversia judicial.")

    # ── CIERRE ──
    doc.add_paragraph()
    p(doc,
      f"Manifestando ambas partes bajo protesta de decir verdad, que en este contrato no existe dolo, "
      f"lesión, mala fe, o algún vicio del consentimiento que pueda afectarle de nulidad, lo leen y "
      f"habiendo quedado plenamente enteradas del contenido y los alcances legales de todas y cada una "
      f"de las cláusulas de este contrato, lo firman de absoluta conformidad por duplicado, al margen "
      f"de cada página anterior y al calce de ésta, en la ciudad de Morelia, Michoacán, a {fecha}.",
      bold=True)

    # ── FIRMAS ──
    doc.add_paragraph()
    from docx.shared import Inches
    # Three signature columns
    table = doc.add_table(rows=1, cols=3)
    table.style = 'Table Grid'
    for cell in table.rows[0].cells:
        cell.width = Cm(6)

    cells = table.rows[0].cells

    def sig_cell(cell, label, nombre):
        p1 = cell.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p1.add_run('\n\n\n_________________________\n').font.size = Pt(10)
        p2 = cell.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p2.add_run(label)
        r.bold = True
        r.font.size = Pt(9)
        p3 = cell.add_paragraph()
        p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r3 = p3.add_run(nombre.upper())
        r3.font.size = Pt(9)

    sig_cell(cells[0], "LA PARTE ARRENDADORA", nombre_arr)
    sig_cell(cells[1], "LA PARTE ARRENDATARIA", nombre_arrta)
    sig_cell(cells[2], "EL OBLIGADO SOLIDARIO", nombre_os)

    # Remove table borders
    for cell in table.rows[0].cells:
        for side in ['top','left','bottom','right']:
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            tcBorders = OxmlElement('w:tcBorders')
            border = OxmlElement(f'w:{side}')
            border.set(qn('w:val'), 'none')
            tcBorders.append(border)
            tcPr.append(tcBorders)

    doc.save(output_path)
    print(f"✓ Contrato de arrendamiento generado: {output_path}")


# ─────────────────────────────────────────────
# PROMESA DE COMPRAVENTA
# ─────────────────────────────────────────────
def generar_promesa(d, output_path):
    doc = setup_doc()

    precio_num, precio_letra  = fmt_monto(d['precio_total'])
    arras_num, arras_letra    = fmt_monto(d['monto_arras'])
    saldo_num, saldo_letra    = fmt_monto(d['monto_saldo'])
    pena_num, pena_letra      = fmt_monto(d.get('pena_convencional', d['monto_arras']))

    fecha         = d['fecha_contrato']
    nombre_vend   = d['nombre_vendedor'].upper()
    nombre_comp   = d['nombre_comprador'].upper()
    dir_inmueble  = d['direccion_inmueble'].upper()
    col_inmueble  = d['colonia_inmueble'].upper()
    cp_inmueble   = d['cp_inmueble']
    escritura_num = d.get('escritura_numero', '___')
    notario_nombre= d.get('notario_nombre', '___')
    notario_num   = d.get('notario_numero', '___')
    tomo          = d.get('tomo_registro', '___')
    registro      = d.get('registro', '___')
    dom_vend      = d['domicilio_vendedor'].upper()
    dom_comp      = d['domicilio_comprador'].upper()
    fecha_limite  = d['fecha_limite_escritura']
    forma_pago    = d.get('forma_pago_saldo', 'efectivo').lower()

    # ── ENCABEZADO ──
    heading(doc, "CONTRATO PRIVADO DE PROMESA DE COMPRAVENTA DE BIEN INMUEBLE")
    doc.add_paragraph()

    p(doc,
      f"CONTRATO PRIVADO DE PROMESA DE COMPRAVENTA QUE CELEBRAN POR UNA PARTE "
      f"{nombre_vend}, PROPIETARIO DEL INMUEBLE UBICADO EN {dir_inmueble}, "
      f"COLONIA {col_inmueble}, CÓDIGO POSTAL {cp_inmueble}, CORRESPONDIENTE AL "
      f"MUNICIPIO DE MORELIA, MICHOACÁN, A QUIEN EN LO SUCESIVO SE LE DENOMINARÁ "
      f"\"EL PROMITENTE VENDEDOR\", Y POR LA OTRA PARTE {nombre_comp}, A QUIEN EN "
      f"LO SUCESIVO SE LE DENOMINARÁ \"EL PROMITENTE COMPRADOR\", SUJETÁNDOSE LAS "
      f"PARTES A LAS SIGUIENTES DECLARACIONES Y CLÁUSULAS:",
      bold=True)

    # ── DECLARACIONES ──
    p(doc, "- - - - - - - - - - - - - D E C L A R A C I O N E S - - - - - - - - - - - - -",
      align=WD_ALIGN_PARAGRAPH.CENTER)

    p(doc,
      f"I.- Declara EL PROMITENTE VENDEDOR, bajo protesta de decir verdad, ser mexicano(a), "
      f"mayor de edad, que es su voluntad celebrar este contrato promisorio y en su oportunidad "
      f"el contrato definitivo respectivo, que tiene las facultades necesarias y que no tiene "
      f"ningún impedimento legal para vender y quien se identifica con su credencial para votar "
      f"emitida por el Instituto Nacional Electoral, que en original exhibe y que se anexa al "
      f"presente instrumento en copia simple.\n\n"
      f"Así mismo, declara bajo protesta de decir verdad, ser el legítimo propietario del "
      f"INMUEBLE UBICADO EN {dir_inmueble}, COLONIA {col_inmueble}, CÓDIGO POSTAL {cp_inmueble}, "
      f"CORRESPONDIENTE AL MUNICIPIO DE MORELIA, MICHOACÁN, lo que demuestra con la escritura "
      f"pública número {escritura_num} pasada ante la fe del {notario_nombre}, notario público "
      f"número {notario_num} en el estado de Michoacán, y debidamente inscrita en el Registro "
      f"Público de la Propiedad bajo el tomo {tomo} y registro {registro} del libro de propiedad; "
      f"que este se encuentra libre de todo gravamen y que no existe impedimento legal alguno para "
      f"vender dicho inmueble.\n\n"
      f"Así mismo EL PROMITENTE VENDEDOR señala como domicilio para recibir cualquier tipo de "
      f"notificación el ubicado en {dom_vend}, CORRESPONDIENTE AL MUNICIPIO DE MORELIA, MICHOACÁN.")

    p(doc,
      f"II.- Declara EL PROMITENTE COMPRADOR, bajo protesta de decir verdad, ser mexicano(a), "
      f"mayor de edad, que es su voluntad celebrar este contrato promisorio y en su oportunidad "
      f"el contrato definitivo respectivo, que tiene las facultades necesarias para comprar, que "
      f"conoce el estado físico y jurídico del inmueble objeto de este contrato y los acepta, y "
      f"quien se identifica con credencial para votar emitida por el Instituto Nacional Electoral, "
      f"que en original exhibe y que se anexa en copia simple al presente instrumento.\n\n"
      f"Además, bajo protesta de decir verdad, manifiesta que los recursos con los que pretende "
      f"adquirir el inmueble objeto de este contrato, son de procedencia lícita.\n\n"
      f"Así mismo señala como domicilio para recibir y oír notificaciones el ubicado en "
      f"{dom_comp}, CORRESPONDIENTE AL MUNICIPIO DE MORELIA, MICHOACÁN.")

    p(doc,
      "III.- Declaran LAS PARTES, bajo protesta de decir verdad, que se reconocen la identidad "
      "de acuerdo a las identificaciones que se describen anteriormente y que se exhiben el uno "
      "al otro en original, que es su voluntad sujetarse en los términos del presente instrumento "
      "y que en este contrato no existe dolo, mala fe, vicios en el consentimiento, ni ningún otro "
      "que lo invalide. Además declaran que no obtienen enriquecimiento ilegítimo.")

    p(doc, "- - - - - - - - - - - - - C L Á U S U L A S - - - - - - - - - - - - -",
      align=WD_ALIGN_PARAGRAPH.CENTER)

    # ── CLÁUSULAS ──
    clausula(doc, "PRIMERA.-", "OBJETO",
        f"El C. {nombre_vend} promete VENDER, y el C. {nombre_comp} promete COMPRAR para sí, "
        f"el inmueble descrito en la declaración I, en el estado físico en que se encuentra, "
        f"que EL PROMITENTE VENDEDOR entregará libre de gravamen, al corriente en sus pagos "
        f"de servicios e impuestos. Así mismo ambos se obligan a celebrar contrato definitivo "
        f"de compraventa ante la fe de un notario público.")

    clausula(doc, "SEGUNDA.-", "PRECIO Y FORMA DE PAGO",
        f"El contrato definitivo de compraventa tendrá un precio pactado de {precio_num} "
        f"({precio_letra}), mismo que será cubierto de la siguiente forma:\n\n"
        f"A) A la firma del presente contrato la cantidad de {arras_num} ({arras_letra}) en "
        f"efectivo, cantidad que será recibida como depósito a título de arras para que en su "
        f"caso dicha cantidad sea aplicada como parte del pago del precio.\n\n"
        f"B) La cantidad de {saldo_num} ({saldo_letra}) mediante {forma_pago} a más tardar "
        f"el {fecha_limite}, previo a la firma de la escritura que certifique el contrato de "
        f"compraventa o simultáneamente a esta.")

    clausula(doc, "TERCERA.-", "ESCRITURA",
        f"Ambas partes aceptan, entienden y se obligan a que la firma de la escritura pública "
        f"que certifique la compraventa sobre el inmueble objeto del presente contrato se celebre "
        f"a más tardar el {fecha_limite}. EL PROMITENTE VENDEDOR se reserva el dominio y "
        f"propiedad del inmueble materia del presente contrato hasta que hayan recibido el importe "
        f"total del precio.")

    clausula(doc, "CUARTA.-", "RESCISIÓN",
        "Serán causas de rescisión del presente instrumento, si alguna de las declaraciones hechas "
        "por las partes resultan falsas; que alguna de las partes no entregue en su totalidad la "
        "documentación requerida para formalizar la compraventa; si la documentación entregada al "
        "notario que formalizará la compraventa es contraria a derecho o falsa; si no se formalizara "
        "el contrato de compraventa a más tardar a la fecha pactada por las partes.")

    clausula(doc, "QUINTA.-", "PENA CONVENCIONAL",
        f"En caso de rescisión del presente contrato por causas imputables a EL PROMITENTE COMPRADOR, "
        f"pagará a EL PROMITENTE VENDEDOR por concepto de pena convencional, la cantidad de {pena_num} "
        f"({pena_letra}), a más tardar 3 días naturales posteriores a la notificación de su "
        f"incumplimiento; mismos que podrán ser pagados con el depósito a título de arras.\n\n"
        f"En el caso de rescisión por causas imputables a EL PROMITENTE VENDEDOR, deberá pagar a "
        f"EL PROMITENTE COMPRADOR la cantidad de {pena_num} ({pena_letra}), a más tardar 3 días "
        f"posteriores a la notificación de su incumplimiento, además de devolver íntegramente todas "
        f"las cantidades que le hayan sido entregadas.")

    clausula(doc, "SEXTA.-", "GASTOS E IMPUESTOS",
        "Acuerdan los contratantes que los gastos, impuestos, derechos y honorarios que se originen "
        "con motivo de la escritura definitiva de compraventa correrán por parte de EL PROMITENTE "
        "COMPRADOR, a excepción del impuesto sobre la renta que en caso de generarse, lo cubrirá "
        "EL PROMITENTE VENDEDOR.")

    clausula(doc, "SÉPTIMA.-", "CONFIDENCIALIDAD",
        "Las partes se obligan a mantener de forma confidencial toda la información y documentación "
        "relativa al presente instrumento y a la operación que prometen llevar a cabo, a no divulgar "
        "a terceros sin el consentimiento previo y por escrito de cualquiera de ellas.")

    clausula(doc, "OCTAVA.-", "VALIDEZ",
        "Si cualquier parte de este contrato se considera inválida o no exigible por un tribunal "
        "competente, las demás partes de este contrato se considerarán válidas y exigibles. "
        "La falta de cualquiera de las partes de exigir los términos y condiciones de este contrato "
        "no se considerarán como una renuncia al derecho de dicha parte de reclamarlos.")

    clausula(doc, "NOVENA.-", "JURISDICCIÓN",
        "Para la interpretación y cumplimiento de cualquier controversia que se pudiera suscitar "
        "con motivo de cumplimiento de las obligaciones que las partes contraen en este contrato, "
        "ambos se someten expresamente a la jurisdicción y tribunales competentes de la ciudad de "
        "Morelia, Michoacán, renunciando a cualquier fuero presente o futuro que les pudiera "
        "corresponder por razón de domicilio.")

    # ── CIERRE ──
    doc.add_paragraph()
    p(doc,
      f"Manifestando ambas partes bajo protesta de decir verdad, que en este contrato no existe "
      f"dolo, mala fe, o algún vicio del consentimiento que pueda afectarle de nulidad, lo leen y "
      f"habiendo quedado enteradas del contenido y los alcances legales de todas y cada una de las "
      f"cláusulas de este contrato, lo firman por duplicado, al margen de cada página anterior y "
      f"al calce de esta, en la ciudad de Morelia, Michoacán, a {fecha}.",
      bold=True)

    # ── FIRMAS ──
    doc.add_paragraph()
    table = doc.add_table(rows=1, cols=2)
    for cell in table.rows[0].cells:
        cell.width = Cm(9)

    cells = table.rows[0].cells

    def sig_cell2(cell, label, nombre):
        p1 = cell.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p1.add_run('\n\n\n_________________________\n').font.size = Pt(10)
        p2 = cell.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p2.add_run(label)
        r.bold = True
        r.font.size = Pt(9)
        p3 = cell.add_paragraph()
        p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r3 = p3.add_run(nombre.upper())
        r3.font.size = Pt(9)

    sig_cell2(cells[0], "EL PROMITENTE VENDEDOR", nombre_vend)
    sig_cell2(cells[1], "EL PROMITENTE COMPRADOR", nombre_comp)

    # Remove table borders
    for cell in table.rows[0].cells:
        for side in ['top','left','bottom','right']:
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            tcBorders = OxmlElement('w:tcBorders')
            border = OxmlElement(f'w:{side}')
            border.set(qn('w:val'), 'none')
            tcBorders.append(border)
            tcPr.append(tcBorders)

    doc.save(output_path)
    print(f"✓ Promesa de compraventa generada: {output_path}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python3 generar_contrato.py <arrendamiento|promesa> <datos.json> <output.docx>")
        sys.exit(1)

    tipo, datos_path, output = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(datos_path) as f:
        datos = json.load(f)

    if tipo == 'arrendamiento':
        generar_arrendamiento(datos, output)
    elif tipo == 'promesa':
        generar_promesa(datos, output)
    else:
        print(f"Tipo desconocido: {tipo}")
        sys.exit(1)
