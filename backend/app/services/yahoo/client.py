import logging
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception_type, stop_after_attempt, wait_exponential

YAHOO_API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"
logger = logging.getLogger(__name__)


class YahooTransientError(Exception):
    def __init__(self, status_code: int, retry_after: float | None = None):
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f"Transient Yahoo API response: {status_code}")


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())


class YahooFantasyClient:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        max_attempts: int = 3,
        base_retry_delay: float = 0.25,
    ):
        self.transport = transport
        self.max_attempts = max_attempts
        self.base_retry_delay = base_retry_delay

    def _wait(self, retry_state: RetryCallState) -> float:
        error = retry_state.outcome.exception() if retry_state.outcome else None
        if isinstance(error, YahooTransientError) and error.retry_after is not None:
            return min(error.retry_after, 5.0)
        return wait_exponential(
            multiplier=self.base_retry_delay,
            min=self.base_retry_delay,
            max=2.0,
        )(retry_state)

    async def get_json(self, path: str, access_token: str) -> dict:
        request_path = path.lstrip("/")

        def log_retry(retry_state: RetryCallState) -> None:
            error = retry_state.outcome.exception() if retry_state.outcome else None
            logger.warning(
                "Retrying Yahoo Fantasy API request",
                extra={
                    "event": "yahoo_request_retry",
                    "path": request_path,
                    "attempt": retry_state.attempt_number,
                    "status_code": getattr(error, "status_code", None),
                },
            )

        async with httpx.AsyncClient(timeout=25, transport=self.transport) as client:
            retrying = AsyncRetrying(
                retry=retry_if_exception_type((YahooTransientError, httpx.TransportError)),
                stop=stop_after_attempt(self.max_attempts),
                wait=self._wait,
                before_sleep=log_retry,
                reraise=True,
            )
            try:
                async for attempt in retrying:
                    with attempt:
                        response = await client.get(
                            f"{YAHOO_API_BASE}/{request_path}",
                            params={"format": "json"},
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        if response.status_code == 401:
                            raise HTTPException(
                                status_code=401,
                                detail="Yahoo rejected the access token; reconnect the account",
                            )
                        if response.status_code == 429 or response.status_code >= 500:
                            raise YahooTransientError(
                                response.status_code,
                                _parse_retry_after(response.headers.get("Retry-After")),
                            )
                        if response.is_error:
                            logger.warning(
                                "Yahoo Fantasy API rejected request",
                                extra={
                                    "event": "yahoo_request_rejected",
                                    "path": request_path,
                                    "status_code": response.status_code,
                                },
                            )
                            raise HTTPException(
                                status_code=502,
                                detail="Yahoo Fantasy API rejected the league request",
                            )
                        try:
                            payload = response.json()
                        except ValueError as error:
                            raise HTTPException(
                                status_code=502,
                                detail="Yahoo Fantasy API returned invalid JSON",
                            ) from error
                        if not isinstance(payload, dict):
                            raise HTTPException(
                                status_code=502,
                                detail="Yahoo Fantasy API returned an unexpected response",
                            )
                        return payload
            except (YahooTransientError, httpx.TransportError) as error:
                logger.error(
                    "Yahoo Fantasy API request exhausted retries",
                    extra={
                        "event": "yahoo_request_failed",
                        "path": request_path,
                        "status_code": getattr(error, "status_code", None),
                        "attempts": self.max_attempts,
                    },
                )
                raise HTTPException(
                    status_code=502,
                    detail="Yahoo Fantasy API is temporarily unavailable",
                ) from error
        raise HTTPException(status_code=502, detail="Yahoo Fantasy API request failed")