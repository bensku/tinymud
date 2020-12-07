"""Database queue support.

Tinymud queues all writes (SELECT, INSERT, UPDATE) to prevent
writes being reordered with each other, or older writes being reordered with
reads. It also allows database access in non-async code.
"""

from asyncio import AbstractEventLoop, Future, Queue, get_event_loop
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List, Optional, Union

from asyncpg import Connection


@dataclass
class _DbRequest:
    """Request to database."""
    callback: Optional[Callable[[], Awaitable[bool]]]
    sql: str
    params: List[Any]


class DbQueue:
    """Database change queue."""
    _loop: AbstractEventLoop
    _queue: Queue[Union[_DbRequest, Future[None]]]

    def __init__(self) -> None:
        self._loop = get_event_loop()
        self._queue = Queue()

    def queue_write(self, callback: Optional[Callable[[], Awaitable[bool]]], sql: str, params: List[Any]) -> None:
        """Queues a write operation to database.

        The callback is executed immediately before the write would be sent
        to database. Returning false discards the write.
        """
        self._queue.put_nowait(_DbRequest(callback, sql, params))

    def wait_for_writes(self) -> Future[None]:
        """Creates a future that will complete after current writes.

        By awaiting on this, caller can make sure that the writes issued before
        this have been completed before e.g. SELECTing from database. Note that
        writes issues after call to this may also have been completed.
        """
        fut = self._loop.create_future()
        self._queue.put_nowait(fut)
        return fut

    async def process_queue(self, conn: Connection) -> None:
        """Processes the write queue.

        This never returns, use asyncio.create_task().
        """
        while True:
            entry = await self._queue.get()
            if isinstance(entry, _DbRequest):  # Execute SQL write
                # Execute callback if it exists
                if entry.callback is None or await entry.callback():
                    # If callback did not exist or returned True, proceed to execute SQL
                    await conn.execute(entry.sql, *entry.params)
            else:  # Just complete futures once we reach them
                entry.set_result(None)
