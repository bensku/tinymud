"""Player characters, monsters and others."""

from dataclasses import dataclass
from typing import Callable, List, Optional, Type, TYPE_CHECKING

from tinymud.entity import Foreign, entity
from .gameobj import GameObj, ObjType, Placeable, _docstring_extract, _register_obj_type
if TYPE_CHECKING:
    from .item import Item, ItemTemplate
    from .place import ChangeFlags, Place
    from .user import Session, User


@dataclass
class CharacterType(ObjType):
    pass


def character(id_str: str) -> Callable[[Type[CharacterType]], CharacterType]:
    def decorator(char_type: Type[CharacterType]) -> CharacterType:
        name, lore = _docstring_extract(char_type)
        instance = char_type('char.' + id_str, name, lore)
        _register_obj_type(instance)
        return instance
    return decorator


@dataclass
class CharacterTemplate:
    """A character template."""
    type: CharacterType
    description: str
    inventory: List['ItemTemplate']


@entity
@dataclass
class Character(GameObj, Placeable):
    """A character in the world.

    A character owned by an user is considered to be a player character.
    All other characters are known as NPCs internally.
    """
    owner: Optional[Foreign['User']]
    _controller: 'Session' = None

    async def inventory(self) -> List['Item']:
        return await Item.select_many(Item.c().owner == self.id)

    async def on_move(self, from_place: Optional['Place'], to_place: 'Place') -> None:
        """Called when this character moves from place to another."""
        if from_place:
            await from_place.on_character_exit(self)
        await to_place.on_character_enter(self)

        # If this has session (and connection, and user), tell them the new location
        if self._controller:
            await self._controller.moved_place(to_place)

    async def move(self, place: 'Place') -> None:
        """Moves this character to a place."""
        place_id = self.place  # type: ignore
        if place_id:  # Initially, a new character has no place
            old_place = await Place.get(place_id)
        else:
            old_place = None
        self.place = place.id
        await self.on_move(old_place, place)

    async def on_tick(self, delta: float, place_changes: 'ChangeFlags') -> None:
        """Called when a place ticks.

        This is not called for characters that are not in any place, or whose
        place is not loaded (for performance reasons).
        """
        # If current place has changed and we have a session, let the client know
        if place_changes != 0 and self._controller:
            await self._controller.place_updated(place_changes)


# FIXME import order hack :(
from .item import Item