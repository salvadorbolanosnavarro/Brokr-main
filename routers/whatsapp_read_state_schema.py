from pydantic import BaseModel


class LecturaReq(BaseModel):
    no_leida: bool = False
