"""
API Gateway — Service 6
Run: python -m services.api_gateway.main
"""
import structlog
from services.api_gateway.app import create_app
import uvicorn
from shared.config import get_settings

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)

app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "services.api_gateway.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
