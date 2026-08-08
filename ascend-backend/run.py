"""Run Ascend with the saved default host and port."""

import uvicorn

from app.core.config import get_settings


def main() -> None:
    """Start the Ascend API server."""
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
