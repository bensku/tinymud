"""Attributes, skills and of course physical items."""

from dataclasses import dataclass
from typing import Callable, Type

from tinymud.entity import entity
from .gameobj import Carriable, GameObj, ObjType, Placeable, _docstring_extract, _register_obj_type


@dataclass
class ItemType(ObjType):
    pass


def item(id_str: str) -> Callable[[Type[ItemType]], Type[ItemType]]:
    def decorator(item_type: Type[ItemType]) -> Type[ItemType]:
        name, lore = _docstring_extract(item_type)
        instance = item_type('item.' + id_str, name, lore)
        _register_obj_type(instance)
        return instance
    return decorator


@entity
@dataclass
class Item(GameObj, Carriable, Placeable):
    """A physical item."""
