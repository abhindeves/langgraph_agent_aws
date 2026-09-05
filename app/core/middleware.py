import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.correlation")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that ensures every request has an X-Request-ID.
    - Uses existing X-Request-ID or X-Correlation-ID from the client if provided.
    - Otherwise generates a new UUID4.
    - Attaches request_id to request.state and returns it in the response headers.
    - Logs structured request start/end metrics with latency.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract or generate correlation id
        request_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Correlation-ID")
            or str(uuid.uuid4())
        )
        request.state.request_id = request_id

        start_time = time.perf_counter()
        logger.info(f"[{request_id}] START {request.method} {request.url.path}")

        try:
            response: Response = await call_next(request)
        except Exception:
            process_time = (time.perf_counter() - start_time) * 1000
            logger.exception(f"[{request_id}] FAILED {request.method} {request.url.path} in {process_time:.2f}ms")
            raise

        process_time = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            f"[{request_id}] COMPLETED {request.method} {request.url.path} "
            f"Status={response.status_code} in {process_time:.2f}ms"
        )
        return response
