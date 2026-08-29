from pydantic import BaseModel


class ConvPatchReq(BaseModel):
    ai_enabled: bool | None = None
    ia_modo: str | None = None
    etapa: str | None = None
