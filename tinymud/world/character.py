"""Player characters, monsters and others."""

from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

from tinymud.entity import Foreign, entity
from .gameobj import GameObj, Placeable
if TYPE_CHECKING:
    from .item import Item
    from .place import Place
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
            self._controller._place_changed(to_place)
