"""Attributes, skills and of course physical items."""

from dataclasses import dataclass
from typing import Callable, Type, Union, TYPE_CHECKING

from tinymud.db import entity
from .character import Character
from .gameobj import Carriable, GameObj, ObjType, Placeable, _docstring_extract, _register_obj_type
if TYPE_CHECKING:
    from .place import Place


@dataclass
class ItemType(ObjType):
    pass


def item(id_str: str) -> Callable[[Type[ItemType]], ItemType]:
    def decorator(item_type: Type[ItemType]) -> ItemType:
        name, lore = _docstring_extract(item_type)
        instance = item_type('item.' + id_str, name, lore)
        _register_obj_type(instance)
        return instance
    return decorator


@dataclass
class ItemTemplate:
    """A template of an item."""
    type: ItemType
    name: str


@entity
@dataclass
class Item(GameObj, Carriable, Placeable):
    """A physical item."""

    def move(self, target: Union['Character', 'Place']) -> None:
        """Moves this item to an inventory of character or a place."""
        if isinstance(target, Character):
            self.owner = target.id
            self.place = None
        else:
            self.owner = None
            self.place = target.id
