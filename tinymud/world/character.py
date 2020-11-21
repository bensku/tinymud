"""Player characters, monsters and others."""

from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

from tinymud.entity import Foreign, entity
from .gameobj import GameObj, Placeable
if TYPE_CHECKING:
    from .item import Item
    from .place import ChangeFlags, Place
    from .user import Session, User


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

    def on_move(self, from_place: 'Place', to_place: 'Place') -> None:
        """Called when this character moves from place to another."""
        from_place.on_character_exit(self)
        to_place.on_character_enter(self)

        # If this has session (and connection, and user), tell them the new location
        if self._controller:
            self._controller.moved_place(to_place)

    def on_tick(self, delta: float, place_changes: 'ChangeFlags') -> None:
        """Called when a place ticks.

        This is not called for characters that are not in any place, or whose
        place is not loaded (for performance reasons).
        """
        # If current place has changed and we have a session, let the client know
        if place_changes != 0 and self._controller:
            self._controller.place_updated(place_changes)
