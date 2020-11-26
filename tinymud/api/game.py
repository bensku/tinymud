"""Game-related APIs (mostly Websocket)."""

from typing import Dict, List, Optional

from aiohttp.web import Application, Request, RouteTableDef, WebSocketResponse
from pydantic import BaseModel

from .auth import validate_token
from tinymud.world.character import Character
from tinymud.world.character import GameObj
from tinymud.world.place import ChangeFlags, Place
from tinymud.world.user import User

game_app = Application()
routes = RouteTableDef()


class OutMessage(BaseModel):
    """Message sent from server to client."""


class VisibleObj(BaseModel):
    """Visible information about GameObj for client."""
    name: str


class UpdatePlace(OutMessage):
    """Update details about current place.

    Data that doesn't need to be updated can be left as None if changes are
    not needed.
    """
    title: Optional[str]
    header: Optional[str]
    passages: Optional[Dict[int, str]]
    characters: Optional[List[VisibleObj]]
    items: Optional[List[VisibleObj]]


class UpdateCharacter(OutMessage):
    """Update details about currently played character."""
    name: Optional[str]
    inventory: Optional[List[VisibleObj]]


class InMessage(BaseModel):
    """Message received by server from client."""


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

        self._character = new_char
        # Also keep the current place loaded
        self._place = await Place.get(new_char.place)

    @property
    def place(self) -> Optional[Place]:
        return self._place

    async def send_msg(self, msg: OutMessage) -> None:
        fields = msg.dict()
        fields['_id'] = type(msg).__name__
        await self.socket.send_json(fields)

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
            characters = self._get_client_objs(place.characters())
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


@routes.get('/ws')
async def game_ws(request: Request) -> WebSocketResponse:
    ws = WebSocketResponse()
    await ws.prepare(request)

    # Wait for client to send JWT auth token
    auth_token = validate_token(await ws.receive())
    user = await User.get(auth_token['user_id'])
    session = Session(user, ws)

    # TODO character creation, multiple characters, etc.
    character = await Character.select(Character.c().owner == user.id)
    if not character:
        pass  # TODO create it
    session.set_character(character)

    # Receive messages and deal with them
    while True:
        msg = await ws.receive_json()
        id = msg._id    


    return ws


game_app.add_routes(routes)