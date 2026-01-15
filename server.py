from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from app.core.config import settings
from app.core.logging import configure_logging
from app.routes.sttRoutes import router as stt_router
from app.routes.ttsRoutes import router as tts_router
from app.routes.healthRoutes import router as health_router
from app.routes.realtimeRoutes import router as rt_router

configure_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create shared HTTP client
    app.state.http_client = httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_S)
    logger.info("HTTP client initialized")
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        logger.info("HTTP client closed")

app = FastAPI(
    title="Speech AI Bridge",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Mount routers with versioning
app.include_router(health_router, prefix="/api/v1")
app.include_router(stt_router, prefix="/api/v1")
app.include_router(tts_router, prefix="/api/v1")
app.include_router(rt_router, prefix="/api/v1")


def get_http_client() -> httpx.AsyncClient:
    """Expose shared HTTP client for modules that cannot use FastAPI dependencies (e.g., WebSocket handlers)."""
    return app.state.http_client