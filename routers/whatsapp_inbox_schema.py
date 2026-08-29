from pydantic import BaseModel


class EnviarManualReq(BaseModel):
    conversacion_id: str
    texto: str
