from pydantic import BaseModel


class PlantillaCrearReq(BaseModel):
    numero_id: str
    nombre: str
    idioma: str = "es_MX"
    categoria: str = "UTILITY"
    cuerpo: str
    variables_ejemplo: list[str] = []
    footer: str | None = None


class PlantillaEnviarReq(BaseModel):
    conversacion_id: str
    nombre: str
    idioma: str
    variables: list[str] = []
