"""Messages sent and received from clients.

These go over WebSocket and are 'realtime'.
"""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel

from tinymud.world import Character, Place, PassageData, UserRoles
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


class UserError(Exception):
    """User error.

    When client cannot validate data, errors of this type should be used.
    The message will be displayed to end-user, so capitalize properly!
    """


async def handle_client_msg(session: Session, msg: Dict[Any, Any]) -> None:
    """Handles a deserialized JSON message from client."""
    cls = _client_msg_types[msg['type']]
    if cls._allowed_roles & session.user.roles == 0:
        raise UnauthorizedMessage(f"user {session.user.name} is missing any of roles {cls._allowed_roles}")

    obj = cls(**msg)  # Use Pydantic to validate and create instance for us to call
    try:
        await obj.on_receive(session)
    except UserError as e:
        logger.debug(f"User error from {session.user.name}: {e}")
        # We'll just send an alert to the client for now
        await session.send_msg(DisplayAlert(alert=str(e)))


class VisibleObj(BaseModel):
    """Visible information about GameObj for client."""
    id: int
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
    passages: Optional[List[PassageData]]
    characters: Optional[List[VisibleObj]]
    items: Optional[List[VisibleObj]]


class UpdateCharacter(ServerMessage):
    """Update details about currently played character."""
    character: VisibleObj
    inventory: Optional[List[VisibleObj]]


class CreateCharacter(ServerMessage):
    """Request client to create a character."""
    options: List[str]


class DisplayAlert(ServerMessage):
    """Shows an alert to the client."""
    alert: str


# Omit _clientmsg, this is special case for now
# TODO revisit when character list support lands
class PickCharacterTemplate(ClientMessage):
    """Respond to character creation prompt."""
    name: str
    selected: int


@_clientmsg(UserRoles.PLAYER)
class UsePassage(ClientMessage):
    """Use a passage to move the played character."""
    address: str

    async def on_receive(self, session: Session) -> None:
        character = session.character
        if not character:
            raise ValueError('cannot move no character')
        from_place = session.place
        if not from_place:
            raise ValueError('cannot use passage out of no place')
        await from_place.use_passage(character, self.address)


@_clientmsg(UserRoles.EDITOR)
class EditorTeleport(ClientMessage):
    """Teleport a character to a place."""
    character: int
    address: str

    async def on_receive(self, session: Session) -> None:
        place = await Place.from_addr(self.address)
        if not place:
            raise UserError(f"Place '{self.address}' does not exist")
        character = await Character.get(self.character)
        if not character:
            raise ValueError('missing character')
        await character.move(place)
        logger.debug(f"Editor {session.user.name} admin-teleported {character.id} to {self.address}")


@_clientmsg(UserRoles.EDITOR)
class EditorPlaceEdit(ClientMessage):
    """Change place title and description."""
    address: str
    title: str
    header: str
    passages: List[PassageData]

    async def on_receive(self, session: Session) -> None:
        place = await Place.from_addr(self.address)
        if not place:  # Client should have known better
            raise ValueError(f"Place {self.address} not found")
        logger.debug(f"Place {place.address} edited by {session.user.name}")
        place.title = self.title
        place.header = self.header
        await place.update_passages(self.passages)


@_clientmsg(UserRoles.EDITOR)
class EditorPlaceCreate(ClientMessage):
    """Create a new place."""
    address: str

    async def on_receive(self, session: Session) -> None:
        place = await Place.from_addr(self.address)
        if place:
            raise UserError(f"Place '{self.address}' already exists")
        # Make place with no content, editor can fill that in later
        Place(address=self.address, title="", header="")


@_clientmsg(UserRoles.EDITOR)
class EditorPlaceDestroy(ClientMessage):
    """Destroy an existing place."""
    address: str

    async def on_receive(self, session: Session) -> None:
        place = await Place.from_addr(self.address)
        if not place:
            raise UserError(f"Place '{self.address}' not found")
        if place.address == 'tinymud.limbo':
            raise UserError("Cannot destroy a system place")

        # Teleport all characters to safety
        limbo = await Place.from_addr('tinymud.limbo')
        assert limbo
        for character in await place.characters():
            await character.move(limbo)

        # Destroy once it is empty
        await place.destroy()
