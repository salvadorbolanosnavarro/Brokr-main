from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile


def create_router(get_context: Callable[[], dict[str, Any]]) -> APIRouter:
    """Create the legacy contact-file import route without mounting it early.

    Dependencies are resolved on every request so mutable compatibility/test
    seams in main.py remain observable during the prepared state.
    """
    router = APIRouter()

    @router.post("/contactos/importar-archivo")
    async def importar_contactos_archivo(request: Request, file: UploadFile = File(...)):
        deps = get_context()
        get_user_id_from_token = deps["get_user_id_from_token"]
        SUPABASE_URL = deps["SUPABASE_URL"]
        SUPABASE_SERVICE_KEY = deps["SUPABASE_SERVICE_KEY"]
        get_org_id_for_user = deps["get_org_id_for_user"]
        get_rows = deps["get_rows"]
        patch_rows = deps["patch_rows"]
        post_rows = deps["post_rows"]
        _mapa_agentes_org = deps["_mapa_agentes_org"]
        httpx = deps["httpx"]
        re = deps["re"]
        _uuid = deps["_uuid"]
        datetime = deps["datetime"]

        user_id = await get_user_id_from_token(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

        nombre_archivo = (file.filename or "").lower()
        contenido = await file.read()
        if not contenido:
            raise HTTPException(status_code=400, detail="El archivo llegó vacío.")
        if len(contenido) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="El archivo pesa más de 15 MB. Divide el export en partes más chicas.")

        filas: list = []
        if nombre_archivo.endswith((".xlsx", ".xls")):
            try:
                import openpyxl
                from io import BytesIO
                wb = openpyxl.load_workbook(BytesIO(contenido), read_only=True, data_only=True)
                hoja = wb.worksheets[0]
                iterador = hoja.iter_rows(values_only=True)
                encabezados = None
                for row in iterador:
                    celdas = ["" if v is None else str(v).strip() for v in row]
                    if encabezados is None:
                        if not any(celdas):
                            continue
                        encabezados = celdas
                        continue
                    if any(celdas):
                        filas.append(dict(zip(encabezados, celdas)))
                wb.close()
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"No se pudo leer el Excel: {str(e)[:150]}")
        else:
            import csv as _csv
            from io import StringIO
            texto = None
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    texto = contenido.decode(enc)
                    break
                except Exception:
                    continue
            if texto is None:
                raise HTTPException(status_code=400, detail="No se pudo leer el archivo. Guárdalo como CSV UTF-8 o Excel.")
            primera = texto.splitlines()[0] if texto.splitlines() else ""
            delim = ";" if primera.count(";") > primera.count(",") else ","
            lector = _csv.DictReader(StringIO(texto), delimiter=delim)
            for row in lector:
                fila = {(k or "").strip(): ("" if v is None else str(v).strip()) for k, v in row.items()}
                if any(fila.values()):
                    filas.append(fila)

        if not filas:
            raise HTTPException(status_code=400, detail="No se encontraron filas con datos. Revisa que la primera fila tenga los encabezados.")

        import unicodedata

        def _norm(t: str) -> str:
            t = unicodedata.normalize("NFD", str(t or ""))
            t = "".join(c for c in t if unicodedata.category(c) != "Mn")
            return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()

        ALIAS = {
            "nombre": ("nombre completo", "nombre", "name", "full name", "contacto", "cliente"),
            "apellido": ("apellidos", "apellido", "last name"),
            "telefono": ("telefono movil", "telefono celular", "telefonos", "telefono", "celular", "movil", "phone", "tel"),
            "wa": ("whatsapp",),
            "email": ("correo electronico", "correos", "correo", "email", "e mail", "mail"),
            "empresa": ("empresa", "compania", "company"),
            "notas": ("descripcion privada", "descripcion", "notas", "comentarios", "notes", "observaciones"),
            "etiquetas": ("etiquetas", "tags"),
            "fuente": ("fuente", "origen", "source"),
            "probabilidad": ("probabilidad", "probability"),
            "estatus": ("estatus", "estado", "etapa", "status"),
            "calle": ("direccion", "calle", "domicilio", "street"),
            "mpio": ("municipio", "ciudad", "city"),
            "cp": ("codigo postal", "cp", "postal code"),
            "fecha": ("fecha de creacion", "fecha de registro", "fecha de alta", "creado", "created at", "fecha"),
            "agente": ("agente asignado", "agente", "asesor", "responsable", "agent"),
            "props": ("codigos de propiedad", "codigo de propiedad", "propiedades", "propiedades de interes", "propiedad", "inmuebles", "properties"),
            "tipo": ("tipo de contacto", "tipo", "rol", "perfil"),
        }
        columnas_archivo = list(filas[0].keys())
        col_de = {}
        usadas = set()
        for campo, alias in ALIAS.items():
            for a in alias:
                for col in columnas_archivo:
                    if col in usadas:
                        continue
                    if a == _norm(col) or (len(a) > 3 and a in _norm(col)):
                        col_de[campo] = col
                        usadas.add(col)
                        break
                if campo in col_de:
                    break

        if "nombre" not in col_de and "telefono" not in col_de and "email" not in col_de:
            raise HTTPException(status_code=400, detail=("No reconocí las columnas del archivo. Necesita al menos una de: "
                        "Nombre, Teléfono o Correo. Columnas recibidas: "
                        + ", ".join(columnas_archivo[:12])))

        _PROB = {"low": "baja", "baja": "baja", "medium": "media", "media": "media",
                 "high": "alta", "alta": "alta"}
        _TIPO = {"comprador": "comprador", "buyer": "comprador",
                 "vendedor": "vendedor", "seller": "vendedor",
                 "propietario": "vendedor", "owner": "vendedor",
                 "arrendador": "arrendador", "arrendatario": "arrendatario",
                 "inquilino": "arrendatario"}
        _RE_EB = re.compile(r"EB-[A-Za-z0-9]{4,10}")

        def _tel_limpio_csv(x):
            t = re.sub(r"[^+\d]", "", str(x or ""))
            return t[:20] if len(t) >= 7 else ""

        def _fecha_iso(x):
            x = str(x or "").strip()
            if not x:
                return None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
                        "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
                try:
                    return datetime.strptime(x[:19], fmt).isoformat()
                except Exception:
                    continue
            return None

        def _valor(fila, campo):
            col = col_de.get(campo)
            return (fila.get(col) or "").strip() if col else ""

        org_id_import = await get_org_id_for_user(user_id)
        filtro_org = ({"org_id": f"eq.{org_id_import}"} if org_id_import
                      else {"user_id": f"eq.{user_id}"})
        sb_headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
        }
        _ = sb_headers
        prop_por_eb_id = {}
        pares_existentes = set()
        async with httpx.AsyncClient(timeout=20) as client:
            _ = client
            try:
                existentes = await get_rows(
                    "contactos",
                    {**filtro_org, "limit": "10000",
                     "select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas,estatus"},
                    timeout=20,
                )
            except httpx.HTTPStatusError:
                existentes = []
            try:
                propiedades_existentes = await get_rows(
                    "propiedades",
                    {**filtro_org, "eb_public_id": "not.is.null",
                     "select": "id,eb_public_id", "limit": "5000"},
                    timeout=20,
                )
            except httpx.HTTPStatusError:
                propiedades_existentes = []
            for row in propiedades_existentes:
                if row.get("eb_public_id"):
                    prop_por_eb_id[row["eb_public_id"]] = row["id"]
            try:
                vinculos_existentes = await get_rows(
                    "contactos_propiedades",
                    {"select": "contacto_id,propiedad_id", "limit": "20000"},
                    timeout=20,
                )
            except httpx.HTTPStatusError:
                vinculos_existentes = []
            for v in vinculos_existentes:
                pares_existentes.add((v.get("contacto_id"), v.get("propiedad_id")))

        por_tel = {_tel_limpio_csv(c.get("telefono")): c for c in existentes if _tel_limpio_csv(c.get("telefono"))}
        por_email = {(c.get("email") or "").strip().lower(): c for c in existentes if c.get("email")}

        mapa_ag = await _mapa_agentes_org(org_id_import, user_id)

        def _user_de_agente_txt(texto):
            t = (texto or "").strip()
            if not t:
                return None
            if "@" in t:
                return mapa_ag["por_email"].get(t.lower())
            return mapa_ag["por_nombre"].get(mapa_ag["_nrm"](t))

        importados = actualizados = omitidos = errores = 0
        vinculos_nuevos = 0
        sin_propiedad = 0

        async with httpx.AsyncClient(timeout=20) as client:
            _ = client
            for fila in filas:
                nombre = _valor(fila, "nombre")
                apellido = _valor(fila, "apellido")
                if apellido and apellido.lower() not in nombre.lower():
                    nombre = f"{nombre} {apellido}".strip()
                nombre = nombre[:120]
                tel = _tel_limpio_csv(_valor(fila, "telefono"))
                wa = _tel_limpio_csv(_valor(fila, "wa"))
                email = _valor(fila, "email").lower()
                if email and ("@" not in email or " " in email):
                    email = ""
                email = email[:120]
                if not nombre and not tel and not email:
                    omitidos += 1
                    continue

                notas = _valor(fila, "notas")[:2000]
                agente = _valor(fila, "agente")
                agente_uid = _user_de_agente_txt(agente)
                if agente and not agente_uid:
                    linea = f"Asesor en EasyBroker: {agente}"
                    notas = (notas + "\n" + linea).strip() if notas else linea
                    notas = notas[:2000]
                etiquetas = [t.strip() for t in re.split(r"[,;|]", _valor(fila, "etiquetas")) if t.strip()][:40]
                fecha_real = _fecha_iso(_valor(fila, "fecha"))
                now_iso = datetime.utcnow().isoformat()

                m = {
                    "nombre": nombre,
                    "telefono": tel,
                    "wa": wa,
                    "email": email,
                    "empresa": _valor(fila, "empresa")[:120],
                    "notas": notas,
                    "etiquetas": etiquetas,
                    "fuente": (_valor(fila, "fuente") or "EasyBroker (archivo)")[:80],
                    "probabilidad": _PROB.get(_valor(fila, "probabilidad").lower()),
                    "estatus": _valor(fila, "estatus").lower()[:40] or None,
                    "calle": _valor(fila, "calle")[:160],
                    "mpio": _valor(fila, "mpio")[:80],
                    "cp": _valor(fila, "cp")[:12],
                }

                codigos = set(_RE_EB.findall(_valor(fila, "props")))
                codigos.update(_RE_EB.findall(notas))

                existente = (por_tel.get(tel) if tel else None) or (por_email.get(email) if email else None)
                if existente:
                    contacto_id = existente["id"]
                    patch = {}
                    for campo in ("nombre", "telefono", "email", "wa", "empresa", "notas",
                                  "fuente", "probabilidad", "estatus", "calle", "mpio", "cp"):
                        if not existente.get(campo) and m.get(campo):
                            patch[campo] = m[campo]
                    if etiquetas:
                        prev = existente.get("etiquetas") or []
                        union = list(dict.fromkeys([*prev, *etiquetas]))
                        if union != prev:
                            patch["etiquetas"] = union
                    if patch:
                        patch["updated_at"] = now_iso
                        try:
                            await patch_rows(
                                "contactos",
                                {"id": f"eq.{contacto_id}"},
                                patch,
                                timeout=20,
                                accepted_statuses=(200, 204),
                            )
                            actualizados += 1
                            existente.update(patch)
                        except httpx.HTTPStatusError:
                            errores += 1
                    else:
                        omitidos += 1
                else:
                    nuevo = {
                        "id": str(_uuid.uuid4()),
                        "user_id": agente_uid or user_id,
                        "org_id": org_id_import,
                        "tipo": _TIPO.get(_valor(fila, "tipo").lower(), "otro"),
                        "created_at": fecha_real or now_iso,
                        "updated_at": now_iso,
                        **m,
                    }
                    nuevo["nombre"] = nombre or "Sin nombre"
                    nuevo = {k: v for k, v in nuevo.items() if v not in ("", None, [])}
                    try:
                        await post_rows(
                            "contactos",
                            nuevo,
                            prefer="return=minimal",
                            timeout=20,
                            accepted_statuses=(200, 201, 204),
                        )
                        importados += 1
                        contacto_id = nuevo["id"]
                        if tel:
                            por_tel[tel] = {"id": contacto_id, **m}
                        if email:
                            por_email[email] = {"id": contacto_id, **m}
                    except httpx.HTTPStatusError:
                        errores += 1
                        continue

                for cod in codigos:
                    propiedad_id = prop_por_eb_id.get(cod)
                    if not propiedad_id:
                        sin_propiedad += 1
                        continue
                    if (contacto_id, propiedad_id) in pares_existentes:
                        continue
                    try:
                        await post_rows(
                            "contactos_propiedades",
                            {"user_id": user_id, "contacto_id": contacto_id,
                             "propiedad_id": propiedad_id, "relacion": "interes"},
                            prefer="return=minimal",
                            timeout=20,
                            accepted_statuses=(200, 201, 204),
                        )
                        vinculos_nuevos += 1
                        pares_existentes.add((contacto_id, propiedad_id))
                    except httpx.HTTPStatusError:
                        pass

        return {
            "ok": True,
            "filas": len(filas),
            "importados": importados,
            "actualizados": actualizados,
            "omitidos": omitidos,
            "vinculos": vinculos_nuevos,
            "sin_propiedad": sin_propiedad,
            "errores": errores,
            "columnas": {k: v for k, v in col_de.items()},
        }

    return router
