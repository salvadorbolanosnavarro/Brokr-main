from pydantic import BaseModel


class ProbarReq(BaseModel):
    numero_id: str | None = None
    historial: list = []
    mensaje: str
