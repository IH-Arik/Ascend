"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.exception_handler(ValidationError)
async def pydantic_validation_error_handler(_: Request, exc: ValidationError) -> JSONResponse:
    """Return a clean 400 instead of a raw 500 traceback.

    Every route with a `{something_id}` path param passes it straight to
    Beanie's `Model.get(id)`, which raises a bare `pydantic.ValidationError`
    (not FastAPI's own `RequestValidationError`, which already gets a clean
    422) when the id isn't a valid `PydanticObjectId` - e.g. a caller left a
    placeholder like "REPLACE_WITH_USER_ID" in the URL. Without this handler
    that error was unhandled and leaked a full stack trace as a 500.
    """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Invalid ID format in the request."},
    )


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    """Return a simple root payload."""
    return {
        "message": f"{settings.app_name} is running.",
        "environment": settings.app_env,
    }
