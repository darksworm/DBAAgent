from __future__ import annotations

import asyncio
import queue
from typing import Set


class EventHub:
    """A tiny thread-safe pub/sub hub for server-sent events.

    - Subscribers receive pre-formatted SSE strings (bytes) via a Queue.
    - `publish(event)` sends an SSE event with the given name to all subscribers.
    """

    def __init__(self) -> None:
        self._subs: Set[queue.Queue[bytes]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> queue.Queue[bytes]:
        q: queue.Queue[bytes] = queue.Queue(maxsize=100)
        async with self._lock:
            self._subs.add(q)
        return q

    async def unsubscribe(self, q: queue.Queue[bytes]) -> None:
        async with self._lock:
            self._subs.discard(q)

    def publish(self, event: str, data: str = "1") -> None:
        payload = (f"event: {event}\n" f"data: {data}\n\n").encode("utf-8")
        # Iterate over a copy to avoid mutation during iteration
        for q in list(self._subs):
            try:
                q.put_nowait(payload)
            except queue.Full:
                # Drop message if subscriber is too slow
                pass


hub = EventHub()

