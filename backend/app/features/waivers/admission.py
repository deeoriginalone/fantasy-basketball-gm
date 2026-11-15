"""Admission control for heavy waiver reads: one at a time, and abandoned as soon as the client leaves.

Every board, best-move, replacements and impact read loads the whole persisted waiver context. On the shared host
(2026-11-15 incident) an idle API was swapped out; the next page load's overlapping reads then paged it back in from a
rotational disk, nginx answered 504 after 60 seconds and the browser gave up, but the reads kept computing for up to
eight minutes while holding database connections, and every retry or horizon switch added another full load.

A heavy read now waits for the single slot before any database dependency runs, so a queued read holds no connection.
If its client disconnects (browser abort, nginx 499/504) while it is queued or loading, the read is cancelled and
logged as 499. Completed reads return exactly what they returned before; scoring and contracts are untouched.
"""
import asyncio
import weakref
from collections.abc import AsyncIterator, Awaitable
from typing import TypeVar

from fastapi import HTTPException, Request

from app.core.timing import record_phase

HEAVY_READ_SLOTS = 1
CLIENT_CLOSED_REQUEST = 499
CLIENT_CLOSED_DETAIL = "The client closed the request; the waiver read was cancelled."
T = TypeVar("T")
# One semaphore per event loop: asyncio primitives must not be shared across loops (tests run several).
_slots: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _slot() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _slots:
        _slots[loop] = asyncio.Semaphore(HEAVY_READ_SLOTS)
    return _slots[loop]


async def _client_gone(request: Request) -> None:
    """Return when the server reports http.disconnect. These GET routes have no body, so nothing else is consumed."""
    while (await request.receive())["type"] != "http.disconnect":
        pass


async def _drain(task: asyncio.Future) -> None:
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001 - the client is gone; only stopping the work matters
        pass


async def heavy_read_slot(request: Request) -> AsyncIterator[None]:
    """Route dependency, resolved before any database dependency: wait for the heavy-read slot or give up with 499."""
    slot = _slot()
    acquire = asyncio.ensure_future(slot.acquire())
    gone = asyncio.ensure_future(_client_gone(request))
    try:
        with record_phase("queue"):
            await asyncio.wait({acquire, gone}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        await _drain(gone)
        await _drain(acquire)
        if not acquire.cancelled() and acquire.exception() is None:
            slot.release()
        raise
    await _drain(gone)
    if not acquire.done():
        await _drain(acquire)
        if not acquire.cancelled():  # the slot was granted while the cancellation was delivered
            slot.release()
        raise HTTPException(CLIENT_CLOSED_REQUEST, CLIENT_CLOSED_DETAIL)
    try:
        yield
    finally:
        slot.release()


async def until_client_leaves(request: Request, work: Awaitable[T]) -> T:
    """Await `work` (the context load and analysis); cancel it and answer 499 if the client disconnects first.

    Analysis already handed to a worker thread finishes in that thread, but its result is discarded.
    """
    task = asyncio.ensure_future(work)
    gone = asyncio.ensure_future(_client_gone(request))
    try:
        await asyncio.wait({task, gone}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        await _drain(gone)
        await _drain(task)
        raise
    await _drain(gone)
    if task.done():
        return task.result()
    await _drain(task)
    raise HTTPException(CLIENT_CLOSED_REQUEST, CLIENT_CLOSED_DETAIL)
