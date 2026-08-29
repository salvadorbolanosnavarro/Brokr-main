from pydantic import BaseModel


class CampanaAudienciaReq(BaseModel):
    numero_id: str
    etiqueta: str | None = None


class CampanaCrearReq(BaseModel):
    numero_id: str
    nombre: str
    plantilla: str
    idioma: str = "es_MX"
    variables: list[str] = []
    etiqueta: str | None = None
