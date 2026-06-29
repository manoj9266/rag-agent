import json
import logging
import sys
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(message)s",
)

logger = logging.getLogger("rag_agent")


def _log(level: str, **fields) -> None:
    record = {"level": level, "ts": time.time(), **fields}
    logger.log(getattr(logging, level.upper()), json.dumps(record))


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        request.state.request_id = request_id

        response = await call_next(request)

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        tenant_id = getattr(request.state, "tenant_id", None)
        session_id = getattr(request.state, "session_id", None)
        tools_used = getattr(request.state, "tools_used", [])

        _log(
            "info",
            request_id=request_id,
            tenant_id=tenant_id,
            method=request.method,
            path=request.url.path,
            session_id=session_id,
            latency_ms=latency_ms,
            status_code=response.status_code,
            tools_used=tools_used,
        )

        return response
