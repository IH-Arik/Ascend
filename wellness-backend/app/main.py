"""Application entrypoint for the Wellness & Performance Tracking API."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.mongodb import init_db
from app.utils.response import error_response

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description=(
        "Async FastAPI backend for wellness and performance tracking, "
        "structured assessments, scoring, and AI-generated insights."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve both legacy unversioned routes, the /api prefix (for Vercel), and versioned `/api/v1` routes.
app.include_router(api_router)
app.include_router(api_router, prefix="/api")
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize application resources on startup."""
    await init_db()


@app.exception_handler(HTTPException)
async def http_exception_handler(
    _: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Return standardized HTTP exception responses."""
    if isinstance(exc.detail, dict) and "success" in exc.detail:
        content = exc.detail
    else:
        content = error_response(str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return standardized validation error responses."""
    validation_errors = {
        ".".join(str(part) for part in err["loc"] if part != "body"): err["msg"]
        for err in exc.errors()
    }
    return JSONResponse(
        status_code=422,
        content=error_response("Validation error.", validation_errors),
    )


@app.get("/health", status_code=200, tags=["health"])
async def health_check() -> dict[str, str]:
    """Return a simple health status payload."""
    return {"status": "ok"}
