from fastapi import APIRouter
from app.schema.schema import HealthResponse

router = APIRouter(tags=["health"])

@router.get("/healthz", response_model=HealthResponse)
async def healthz():
    return HealthResponse(status="ok")

@router.get("/readyz", response_model=HealthResponse)
async def readyz():
    # Tambahkan checks (env, service reachability) jika perlu
    return HealthResponse(status="ready")