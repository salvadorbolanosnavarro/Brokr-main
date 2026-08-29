from pydantic import BaseModel


class NotaReq(BaseModel):
    texto: str
