import asyncio


class EventBroker:
    """In-process SSE fan-out for this single-instance demo."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event_name: str) -> None:
        for queue in self._subscribers.copy():
            queue.put_nowait(event_name)


broker = EventBroker()
