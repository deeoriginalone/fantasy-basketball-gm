"""Per-request timing for waiver reads: phase durations and counts only, never payloads.

`RequestTimingMiddleware` gives every `/api/` response an `X-Request-ID` (reusing a sane incoming
one, such as the nginx `$request_id`, so proxy timeouts and API logs correlate). For timed routes it
adds a `Server-Timing` header and writes one log line through uvicorn's configured logger.
"""
import logging
import re
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from urllib.parse import parse_qs

# uvicorn configures this logger at INFO; the API process configures no other logging.
logger = logging.getLogger("uvicorn.error")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


@dataclass
class RequestTiming:
    request_id: str
    phases: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)


_current: ContextVar[RequestTiming | None] = ContextVar("request_timing", default=None)


def current_request_id() -> str | None:
    timing = _current.get()
    return timing.request_id if timing is not None else None


@contextmanager
def record_phase(name: str) -> Iterator[None]:
    timing = _current.get()
    started = time.perf_counter()
    try:
        yield
    finally:
        if timing is not None:
            timing.phases[name] = timing.phases.get(name, 0.0) + (time.perf_counter() - started) * 1000


def record_count(name: str, value: int) -> None:
    timing = _current.get()
    if timing is not None:
        timing.counts[name] = value


class RequestTimingMiddleware:
    def __init__(self, app, timed_prefix: str = "/api/v1/waivers", untimed_paths: tuple[str, ...] = ()):
        self.app = app
        self.timed_prefix = timed_prefix
        self.untimed_paths = untimed_paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
        timing = RequestTiming(request_id)
        timed = scope["path"].startswith(self.timed_prefix) and not (
            scope["method"] == "GET" and scope["path"] in self.untimed_paths)
        token = _current.set(timing)
        started = time.perf_counter()
        status = 500

        async def send_with_headers(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [*message.get("headers", []), (b"x-request-id", request_id.encode())]
                if timed:
                    parts = [f"{name};dur={value:.0f}" for name, value in timing.phases.items()]
                    parts.append(f"total;dur={(time.perf_counter() - started) * 1000:.0f}")
                    headers.append((b"server-timing", ", ".join(parts).encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            _current.reset(token)
            if timed:
                mode = parse_qs(scope.get("query_string", b"").decode("latin-1")).get("mode", ["-"])[0]
                logger.info(
                    "request_timing request_id=%s method=%s path=%s mode=%s status=%s total_ms=%.0f %s %s",
                    request_id, scope["method"], scope["path"], mode[:20], status,
                    (time.perf_counter() - started) * 1000,
                    " ".join(f"{name}_ms={value:.0f}" for name, value in timing.phases.items()),
                    " ".join(f"{name}={value}" for name, value in timing.counts.items()),
                )
