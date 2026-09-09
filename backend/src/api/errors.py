from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """An error with a stable machine-readable `code`, per contracts/api.md error shape."""

    def __init__(
        self, code: str, message: str, status_code: int = 400, details: dict | None = None
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content={
                "error": {"code": self.code, "message": self.message, "details": self.details}
            },
        )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:  # noqa: ARG001
    return exc.to_response()
