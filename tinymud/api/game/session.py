"""Game session management.

A session consists of a WebSocket connection to a client, an user that the
clients has authenticated and a character controlled by them.
"""
from typing import Dict, Iterable, List, Optional, Type, TypeVar

from aiohttp.web import WebSocketResponse, WSMsgType

from .message import ClientMessage, ServerMessage, VisibleObj
from .message import CreateCharacter, PickCharacterTemplate, UpdateCharacter, UpdatePlace
from tinymud.game import game_hooks
from tinymud.world import ChangeFlags, Character, GameObj, Place, User


T = TypeVar('T', bound=ClientMessage)


class SocketClosed(Exception):
    """Raised when a WebSocket is closed."""


class Session:
    """Session of logged-in user."""
    user: User
    socket: WebSocketResponse
    _character: Optional[Character]
    _place: Optional[Place]

    def __init__(self, user: User, socket: WebSocketResponse):
        self.user = user
        self.socket = socket
        self._character = None
        self._place = None

    @property
    def character(self) -> Optional[Character]:
        return self._character

    async def set_character(self, new_char: Character) -> None:
        """Sets character of this session.

        Permission checks are done to ensure this is allowed.
        """
        if new_char.owner != self.user.id:  # Permission check
            raise ValueError(f"user {self.user.name} not allowed to control character id {new_char.id}")

        if self._character:  # Detach from previous character, if any
            self._character._controller = None

        # Assuming direct control
        self._character = new_char
        new_char._controller = self

        # Send character updates to client
        await self.send_msg(UpdateCharacter(name=new_char.name,
            inventory=self._get_client_objs(await new_char.inventory())))
        # Also keeps current place in memory due to self._place
        print(new_char)
        await self.moved_place(await Place.get(new_char.place))

    @property
    def place(self) -> Optional[Place]:
        return self._place

    async def send_msg(self, msg: ServerMessage) -> None:
        fields = msg.dict()
        fields['type'] = type(msg).__name__
        await self.socket.send_json(fields)

    async def receive_msg(self, type: Type[T]) -> T:
        msg = await self.socket.receive()
        if msg.type == WSMsgType.CLOSE:
            raise SocketClosed()  # Session is over
        content = msg.json()
        if content['type'] != type.__name__:
            raise ValueError(f"expected message type {type.__name__}, but got {content['type']}")
        return type(**content)

    def _get_client_objs(self, objs: Iterable[GameObj]) -> List[VisibleObj]:
        """Gets objects that can be sent to client.

        Only public information from GameObjs is extracted for sending.
        In future, there might also be checks for visibility etc.
        """
        visible: List[VisibleObj] = []
        for obj in objs:
            visible.append(VisibleObj(name=obj.name))
        return visible

    async def place_updated(self, changes: ChangeFlags) -> None:
        """Called when current place changes.

        Changed data is (re-)sent to client.
        """
        place = self.place
        if place is None:
            raise ValueError("place_updated with missing place")

        # Get passage names by target ids
        # TODO where passage names come from, target place titles?
        passages: Optional[Dict[int, str]]
        if changes & ChangeFlags.PASSAGES:
            passages = {}
            for passage in await place.passages():
                passages[passage.target] = passage.name
        else:
            passages = None

        # TODO characters, items
        characters: List[VisibleObj]
        if changes & ChangeFlags.CHARACTERS:
            characters = self._get_client_objs(await place.characters())
        else:
            passages = None
        items: List[VisibleObj] = []  # TODO item support

        payload = UpdatePlace(
            address=place.address,  # TODO don't send every time
            title=place.title if changes & ChangeFlags.DETAILS else None,
            header=place.header if changes & ChangeFlags.DETAILS else None,
            passages=passages,
            characters=characters,
            items=items
        )
        await self.send_msg(payload)

    async def moved_place(self, new_place: Place) -> None:
        """Called when a different place is moved to.

        Sends ALL data about the place to client.
        """
        self._place = new_place
        await self.place_updated(ChangeFlags.DETAILS | ChangeFlags.PASSAGES |
                ChangeFlags.CHARACTERS | ChangeFlags.ITEMS)


async def create_character(session: Session) -> Character:
    """Goes through character creation with the client."""
    options = await game_hooks().get_character_options(session.user)
    descriptions = [option.description for option in options]

    # Tell client their options, wait for them to pick one (or quit)
    await session.send_msg(CreateCharacter(options=descriptions))
    response = await session.receive_msg(PickCharacterTemplate)
    template = options[response.selected]

    # TODO game name validation hook (for e.g. unique names)

    # Create the character and move it to starting place
    character = Character(place=None, obj_type_id=template.type.id, name=response.name, owner=session.user.id)
    place = await game_hooks().get_starting_place(character, session.user)
    await character.move(place)  # Won't send anything to client, session not attached
    return character
