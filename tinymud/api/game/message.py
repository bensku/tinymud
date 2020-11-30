"""Messages sent and received from clients.

These go over WebSocket and are 'realtime'.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel


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
