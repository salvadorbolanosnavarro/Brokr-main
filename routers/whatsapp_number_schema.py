from pydantic import BaseModel


class NumeroPatchReq(BaseModel):
    alias: str | None = None
    ia_enabled: bool | None = None
    numero_personal: str | None = None
