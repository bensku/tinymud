"""User management."""

from dataclasses import dataclass
from typing import List, Optional
from asyncio.queues import Queue

import argon2

from tinymud.entity import Entity, entity
from .character import Character
from .place import Place


@entity
@dataclass
class User(Entity):
    """Tinymud user.

    Each user may have one or more player characters, that is, characters
    they're allowed to play. Privileged users might also be able to control
    other characters.
    """
    name: str
    password_hash: str  # argon2 hash, not cleartext password!

    @property
    async def owned_characters(self) -> List[Character]:
        return await Character.select_many(Character.c().owner == self.id)


class InvalidCredentials(Exception):
    """Raised when credentials didn't match."""


_hasher = argon2.PasswordHasher()


async def validate_credentials(name: str, password: str) -> User:
    """Validates credentials.

    If an user with given name and password exists, it is returned.
    Otherwise, a InvalidCredentials error is raised.
    """
    user = await User.select(User.c().name == name)
    if not user:
        raise InvalidCredentials()

    # Found user, check if passwords match
    try:
        _hasher.verify(user.password_hash, password)
    except:  # noqa: E722
        # No matter why it failed, can't allow login
        # TODO log 'unusual' failures (e.g. invalid hashes in DB)
        raise InvalidCredentials()

    return user  # Everything passed, give caller the user


class SessionEvent:
    """An event that the client might want to know about."""


@dataclass
class PlaceChanged(SessionEvent):
    """Sent when viewed place changes."""
    new_place: Place


@dataclass
class PlaceUpdated:
    """Sent when current place updates."""


class Session:
    """Session of logged-in user."""
    user: User
    event_queue: Queue[SessionEvent]
    _character: Optional[Character]
    _place: Optional[Place]

    def __init__(self, user: User, event_queue: Queue[SessionEvent]):
        self.user = user
        self.event_queue = event_queue
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

    def _place_changed(self, new_place: Place) -> None:
        self.event_queue.put(new_place)
        self._place = new_place
