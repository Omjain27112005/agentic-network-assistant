"""
FastAPI Application Factory — creates and configures the FastAPI app.

Configuration includes:
- CORS middleware (React dev server on port 5173)
- Lifespan events (startup/shutdown for Redis + DB connections)
- Router registration (devices, alerts, incidents, chat, websocket)
- Global exception handler for clean error responses
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.config import get_settings
from shared.redis_client import get_redis_client

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    FastAPI lifespan context manager.
    Code before yield = startup. Code after yield = shutdown.
    """
    settings = get_settings()

    # Startup: initialize Redis connection
    logger.info("api_gateway.startup")
    try:
        get_redis_client(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
        )
        logger.info("redis.connected")
    except Exception as e:
        logger.error("redis.connection_failed", error=str(e))

    yield  # App is running

    # Shutdown
    logger.info("api_gateway.shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Agentic Network Assistant API",
        description=(
            "Real-time network monitoring API powered by AI. "
            "Provides live device metrics, alerts, incidents, and AI chat."
        ),
        version="1.0.0",
        docs_url="/docs",       # Swagger UI
        redoc_url="/redoc",     # ReDoc UI
        lifespan=lifespan,
    )

    # CORS — allow React dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler — never expose raw tracebacks to client
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            "api.unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)[:100]},
        )

    # Register routers
    from services.api_gateway.routes import devices, alerts, incidents, chat, websocket

    app.include_router(devices.router,   prefix="/api/v1", tags=["Devices"])
    app.include_router(alerts.router,    prefix="/api/v1", tags=["Alerts"])
    app.include_router(incidents.router, prefix="/api/v1", tags=["Incidents"])
    app.include_router(chat.router,      prefix="/api/v1", tags=["AI Chat"])
    app.include_router(websocket.router, prefix="/ws",     tags=["WebSocket"])

    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check endpoint for load balancers and monitoring."""
        return {"status": "healthy", "service": "api-gateway", "version": "1.0.0"}

    return app
