"""Messages sent and received from clients.

These go over WebSocket and are 'realtime'.
"""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel

from tinymud.world import Place, UserRoles
if TYPE_CHECKING:
    from .session import Session


class ClientMessage(BaseModel):
    """Message received by server from client."""
    _allowed_roles: UserRoles

    async def on_receive(self, session: Session) -> None:
        """Called when a message is received from client."""
        pass


class ServerMessage(BaseModel):
    """Message sent from server to client."""


_client_msg_types: Dict[str, Type[ClientMessage]] = {}
T = TypeVar('T', bound=ClientMessage)


def _clientmsg(allowed_roles: UserRoles = UserRoles.PLAYER) -> Callable[[Type[T]], Type[T]]:
    def _decorator(type: Type[T]) -> Type[T]:
        type._allowed_roles = allowed_roles
        if issubclass(type, ClientMessage):
            _client_msg_types[type.__name__] = type
        return type
    return _decorator


class UnauthorizedMessage(Exception):
    """Raised when client sends message without required role."""


async def handle_client_msg(session: Session, msg: Dict[Any, Any]) -> None:
    """Handles a deserialized JSON message from client."""
    cls = _client_msg_types[msg['type']]
    if cls._allowed_roles & session.user.roles == 0:
        raise UnauthorizedMessage(f"user {session.user.name} is missing any of roles {cls._allowed_roles}")

    obj = cls(**msg)  # Use Pydantic to validate and create instance for us to call
    await obj.on_receive(session)


class VisibleObj(BaseModel):
    """Visible information about GameObj for client."""
    name: str


class ClientConfig(ServerMessage):
    """Client configuration options."""
    roles: UserRoles


class UpdatePlace(ServerMessage):
    """Update details about current place.

    Data that doesn't need to be updated can be left as None if changes are
    not needed.
    """
    address: str
    title: Optional[str]
    header: Optional[str]
    passages: Optional[Dict[int, str]]
    characters: Optional[List[VisibleObj]]
    items: Optional[List[VisibleObj]]


class UpdateCharacter(ServerMessage):
    """Update details about currently played character."""
    name: Optional[str]
    inventory: Optional[List[VisibleObj]]


class CreateCharacter(ServerMessage):
    """Request client to create a character."""
    options: List[str]


# Omit _clientmsg, this is special case for now
# TODO revisit when character list support lands
class PickCharacterTemplate(ClientMessage):
    """Respond to character creation prompt."""
    name: str
    selected: int


@_clientmsg(UserRoles.EDITOR)
class PlaceEditMessage(ClientMessage):
    """Change place title and description."""
    address: str
    title: str
    header: str

    async def on_receive(self, session: Session) -> None:
        place = await Place.from_addr(self.address)
        if not place:
            raise ValueError(f"place {self.address} not found")
        logger.debug(f"place {place.address} edited by {session.user.name}")
        place.title = self.title
        place.header = self.header


@_clientmsg(UserRoles.EDITOR)
class PlaceCreateMessage(ClientMessage):
    """Create a new place."""
    address: str

    async def on_receive(self, session: Session) -> None:
        place = await Place.from_addr(self.address)
        if place:
            raise ValueError(f"place ar {self.address} already exists")
        # Make place with no content, editor can fill that in later
        Place(address=self.address, title="", header="")


@_clientmsg(UserRoles.EDITOR)
class PlaceDestroyMessage(ClientMessage):
    """Destroy an existing place."""
    address: str

    async def on_receive(self, session: Session) -> None:
        place = await Place.from_addr(self.address)
        if not place:
            raise ValueError(f"place {self.address} not found")
        await place.destroy()
