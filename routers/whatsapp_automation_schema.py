from pydantic import BaseModel


_AUTO_TIPOS = ("mensaje", "etiqueta", "humano", "ia", "pregunta", "opciones")
_FLUJO_CAMPOS = ("nombre", "presupuesto", "interes", "nota")
_AUTO_COOLDOWN_SEG = 120


class AutomatizacionReq(BaseModel):
    nombre: str
    numero_id: str | None = None
    disparador: str = "palabra"
    palabras: list[str] = []
    acciones: list[dict] = []
    activa: bool = True