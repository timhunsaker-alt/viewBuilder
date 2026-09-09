import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("viewbuilder")
audit_logger = logging.getLogger("viewbuilder.audit")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def log_audit_event(
    *,
    action: str,
    operator: str,
    resource: str,
    resource_id: object,
    version: object = None,
    details: dict | None = None,
) -> None:
    """Structured audit log line for a mutating request (T068).

    Emitted on every request that creates or versions a `mapping_definition`,
    `mapping_version`, `enum_translation_table`, `enum_translation_version`, or that
    dry-runs/executes a mapping (`POST /mappings`, `POST /mappings/{id}/versions`,
    `POST /enum-translations`, `POST /enum-translations/{id}/versions`,
    `POST /mappings/{id}/dry-run`, `POST /mappings/{id}/execute`) — captures who did it
    (`operator`), what happened (`action`), and which mapping/translation version was
    involved, per Constitution Principle I/II (every migration-relevant action must be
    reconstructable after the fact). This is deliberately a plain structured log line
    (not a DB write) — the durable, queryable record of *runs* is `run_log_entry`
    (FR-014); this line is the audit trail for the *definitional* mutations (creating/
    versioning mappings and translation tables) that `run_log_entry` alone doesn't cover.
    """
    audit_logger.info(
        "audit action=%s operator=%s resource=%s resource_id=%s version=%s details=%s",
        action,
        operator,
        resource,
        resource_id,
        version,
        details or {},
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured request logging: method, path, status, duration, and a request id.

    Mutating endpoints additionally log an audit line (operator/action) — see T068 for the
    per-endpoint audit-logging extension; this middleware covers the baseline for every
    request.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = str(uuid.uuid4())
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000
        response.headers["X-Request-Id"] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
