from fastapi import FastAPI

from src.api.errors import ApiError, api_error_handler
from src.api.middleware import RequestLoggingMiddleware, configure_logging

configure_logging()

app = FastAPI(title="viewBuilder API", version="1")
app.add_middleware(RequestLoggingMiddleware)
app.add_exception_handler(ApiError, api_error_handler)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _mount_routers() -> None:
    # Imported lazily so a router module can be added incrementally without breaking
    # `from src.api.main import app` before all routers exist.
    from src.api import connections, mappings  # noqa: PLC0415

    app.include_router(connections.router, prefix="/api/v1")
    app.include_router(mappings.router, prefix="/api/v1")


_mount_routers()
