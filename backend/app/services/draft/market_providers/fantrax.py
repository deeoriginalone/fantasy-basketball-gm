import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from math import isfinite
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.services.draft.market_providers.base import DraftMarketRecord

FANTRAX_ADP_URL = "https://www.fantrax.com/fxea/general/getAdp"
FANTRAX_PLAYER_IDS_URL = "https://www.fantrax.com/fxea/general/getPlayerIds"
FANTRAX_SOURCE = "fantrax"
logger = logging.getLogger(__name__)


class FantraxTransientError(Exception):
    def __init__(self, status_code: int, retry_after: float | None = None):
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f"Transient Fantrax API response: {status_code}")


def _retry_after(value: str | None) -> float | None:
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


def parse_fantrax_adp(
    payload: Any,
    season: str,
    *,
    player_metadata: dict[str, Any] | None = None,
    fetched_at: datetime | None = None,
) -> list[DraftMarketRecord]:
    if not re.fullmatch(r"\d{4}-\d{2}", season):
        raise ValueError("season must use YYYY-YY format")
    if not isinstance(payload, list) or not payload:
        raise ValueError("Fantrax ADP response must be a non-empty list")
    retrieved_at = fetched_at or datetime.now(timezone.utc)
    if retrieved_at.tzinfo is None:
        raise ValueError("fetched_at must include a timezone")

    records = []
    seen_ids: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("Fantrax ADP response contains a non-object record")
        source_player_id = str(row.get("id") or "").strip()
        player_name = str(row.get("name") or "").strip()
        if not source_player_id or not player_name:
            raise ValueError("Fantrax ADP record is missing ID or name")
        if source_player_id in seen_ids:
            raise ValueError("Fantrax ADP response contains duplicate player IDs")
        seen_ids.add(source_player_id)
        metadata = (player_metadata or {}).get(source_player_id)
        if not isinstance(metadata, dict):
            raise ValueError("Fantrax ADP player is missing its ID crosswalk")
        if str(metadata.get("fantraxId") or "").strip() != source_player_id:
            raise ValueError("Fantrax player ID crosswalk is inconsistent")
        position = str(metadata.get("position") or row.get("pos") or "").strip().upper()
        if not position:
            raise ValueError("Fantrax player-ID crosswalk is missing position")
        team = str(metadata.get("team") or "").strip().upper()
        if team in {"", "FA", "N/A", "(N/A)", "FREE AGENT"}:
            team = ""
        try:
            adp = float(row["ADP"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Fantrax ADP record has an invalid ADP value") from error
        if not isfinite(adp) or adp <= 0:
            raise ValueError("Fantrax ADP must be finite and positive")
        records.append(DraftMarketRecord(
            internal_player_id=None,
            source_player_id=source_player_id,
            player_name=player_name,
            team=team or None,
            positions=tuple(value.strip() for value in re.split(r"[,/]", position) if value.strip()),
            adp=adp,
            draft_rank=None,
            xrank=None,
            draft_frequency=None,
            sample_size=None,
            source=FANTRAX_SOURCE,
            season=season,
            fetched_at=retrieved_at,
            source_updated_at=None,
        ))
    return records


class FantraxDraftMarketProvider:
    name = FANTRAX_SOURCE

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 15.0,
        max_attempts: int = 3,
        base_retry_delay: float = 0.5,
    ):
        self.transport = transport
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.base_retry_delay = base_retry_delay

    def _wait(self, retry_state: RetryCallState) -> float:
        error = retry_state.outcome.exception() if retry_state.outcome else None
        if isinstance(error, FantraxTransientError) and error.retry_after is not None:
            return min(error.retry_after, 10.0)
        return wait_exponential(
            multiplier=self.base_retry_delay,
            min=self.base_retry_delay,
            max=4.0,
        )(retry_state)

    async def _get_json(self, endpoint: str) -> Any:
        def log_retry(retry_state: RetryCallState) -> None:
            error = retry_state.outcome.exception() if retry_state.outcome else None
            logger.warning(
                "Retrying Fantrax ADP request",
                extra={
                    "event": "fantrax_adp_retry",
                    "attempt": retry_state.attempt_number,
                    "status_code": getattr(error, "status_code", None),
                },
            )

        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            retrying = AsyncRetrying(
                retry=retry_if_exception_type((FantraxTransientError, httpx.TransportError)),
                stop=stop_after_attempt(self.max_attempts),
                wait=self._wait,
                before_sleep=log_retry,
                reraise=True,
            )
            async for attempt in retrying:
                with attempt:
                    response = await client.get(
                        endpoint,
                        params={"sport": "NBA"},
                        headers={"Accept": "application/json"},
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        raise FantraxTransientError(
                            response.status_code,
                            _retry_after(response.headers.get("Retry-After")),
                        )
                    if response.is_error:
                        raise RuntimeError(f"Fantrax ADP API returned HTTP {response.status_code}")
                    try:
                        return response.json()
                    except ValueError as error:
                        raise ValueError("Fantrax ADP API returned invalid JSON") from error
        raise RuntimeError("Fantrax ADP request failed")

    async def fetch(self, season: str) -> list[DraftMarketRecord]:
        payload = await self._get_json(FANTRAX_ADP_URL)
        player_metadata = await self._get_json(FANTRAX_PLAYER_IDS_URL)
        if not isinstance(player_metadata, dict):
            raise ValueError("Fantrax player-ID crosswalk must be a JSON object")
        return parse_fantrax_adp(
            payload,
            season,
            player_metadata=player_metadata,
        )