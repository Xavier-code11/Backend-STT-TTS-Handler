from pydantic import BaseModel

class STTResponse(BaseModel):
    transcript: str

class ChatResponse(BaseModel):
    # Struktur mengikuti respons n8n (sesuaikan bila perlu)
    type: str
    text: str
    crisis_flag: bool | None = None
    meta: dict | None = None

class HealthResponse(BaseModel):
    status: str