"""Database queue support.

Tinymud queues all writes (SELECT, INSERT, UPDATE) to prevent
writes being reordered with each other, or older writes being reordered with
reads. It also allows database access in non-async code.
"""

from asyncio import AbstractEventLoop, Future, Queue, get_event_loop
from dataclasses import dataclass
from typing import Any, List, Optional, Union, TYPE_CHECKING

from asyncpg import Connection

if TYPE_CHECKING:
    from .entity import Entity


@dataclass
class _DbRequest:
    """Request to database."""
    obj_ref: Optional['Entity']
    sql: str
    params: List[Any]


class DbQueue:
    """Database change queue."""
    _loop: AbstractEventLoop
    _queue: Queue[Union[_DbRequest, Future[None]]]

    def __init__(self) -> None:
        self._loop = get_event_loop()
        self._queue = Queue()

    def queue_write(self, obj_ref: Optional['Entity'], sql: str, params: List[Any]) -> None:
        """Queues a write operation to database.

        First parameter (obj_ref) is used to avoid executing SQL to write
        deleted entities. Leave empty if you don't want that.
        """
        self._queue.put_nowait(_DbRequest(obj_ref, sql, params))

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
                # But don't do it if entity it is associated with has been destroyed
                if not entry.obj_ref or not entry.obj_ref._destroyed:
                    await conn.execute(entry.sql, *entry.params)
            else:  # Just complete futures once we reach them
                entry.set_result(None)
