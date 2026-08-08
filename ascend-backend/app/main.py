"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import close_db
from app.core.database import init_db
from app.core.logging import configure_logging
from app.core.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize lightweight application resources."""
    settings = get_settings()
    configure_logging(settings.log_level)
    await init_db()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()
        await close_db()


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    """Return a simple root payload."""
    return {
        "message": f"{settings.app_name} is running.",
        "environment": settings.app_env,
    }
