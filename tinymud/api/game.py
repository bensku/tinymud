"""Game-related APIs (mostly Websocket)."""

from typing import Dict, List, Optional, Type, TypeVar

from aiohttp.web import Application, Request, RouteTableDef, WebSocketResponse, WSMsgType
from pydantic import BaseModel

from .auth import validate_token
from tinymud.game import game_hooks
from tinymud.world.character import Character, CharacterTemplate
from tinymud.world.character import GameObj
from tinymud.world.place import ChangeFlags, Place
from tinymud.world.user import User

game_app = Application()
routes = RouteTableDef()


class ServerMessage(BaseModel):
    """Message sent from server to client."""


class VisibleObj(BaseModel):
    """Visible information about GameObj for client."""
    name: str


class UpdatePlace(ServerMessage):
    """Update details about current place.

    Data that doesn't need to be updated can be left as None if changes are
    not needed.
    """
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


class ClientMessage(BaseModel):
    """Message received by server from client."""


class PickCharacterTemplate(ClientMessage):
    """Respond to character creation prompt."""
    name: str
    selected: int


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
        if new_char.owner != self.user.id:  # Permission check{type: 'PickCharacterTemplate', name: characterName.value, selected: index}
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
            raise SocketClosed() # Session is over
        content = msg.json()
        if content['type'] != type.__name__:
            raise ValueError(f"expected message type {type.__name__}, but got {content['type']}")
        return type(**content)

    def _get_client_objs(self, objs: List[GameObj]) -> List[VisibleObj]:
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
        characters: List[Character]
        if changes & ChangeFlags.CHARACTERS:
            characters = self._get_client_objs(await place.characters())
        else:
            passages = None
        items: List[VisibleObj] = []  # TODO item support

        payload = UpdatePlace(
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


@routes.get('/ws')
async def game_ws(request: Request) -> WebSocketResponse:
    ws = WebSocketResponse()
    await ws.prepare(request)

    # Wait for client to send JWT auth token
    auth_token = validate_token((await ws.receive()).data)
    user = await User.get(auth_token['user_id'])
    session = Session(user, ws)

    # TODO character select screen (full multi character support)
    character = await Character.select(Character.c().owner == user.id)
    if not character:
        character = await create_character(session)
    await session.set_character(character)  # Take control of the character

    # Receive messages and deal with them
    while True:
        # session.receive_msg() expects type, which we don't know
        msg = await ws.receive_json()
        type_id = msg.type


    return ws


game_app.add_routes(routes)
