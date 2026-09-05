import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from openai import APIConnectionError, AuthenticationError, RateLimitError

logger = logging.getLogger("app.errors")


def register_exception_handlers(app: FastAPI):
    """
    Register centralized exception handlers for standardizing API error responses.
    """

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(request: Request, exc: RateLimitError):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.warning(f"[{request_id}] OpenAI Rate Limit Exceeded: {exc}")
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "The AI model provider is currently rate limited. Please retry in a few moments.",
                    "request_id": request_id,
                }
            },
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(AuthenticationError)
    async def auth_error_handler(request: Request, exc: AuthenticationError):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(f"[{request_id}] OpenAI Authentication Failed: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "PROVIDER_AUTH_ERROR",
                    "message": "Authentication with the AI provider failed. Check server credentials.",
                    "request_id": request_id,
                }
            },
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(APIConnectionError)
    async def connection_error_handler(request: Request, exc: APIConnectionError):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(f"[{request_id}] OpenAI Connection Error: {exc}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "PROVIDER_UNAVAILABLE",
                    "message": "Unable to reach the AI model provider. Please check network connectivity.",
                    "request_id": request_id,
                }
            },
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception(f"[{request_id}] Unhandled Server Error: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred while processing your request.",
                    "request_id": request_id,
                }
            },
            headers={"X-Request-ID": request_id},
        )
