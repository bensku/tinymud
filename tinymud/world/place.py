"""Rooms are places in the world."""

from dataclasses import dataclass
from typing import Dict, List

from tinymud.entity import entity, Foreign
from .character import CachedCharacter
from .gameobj import GameObj, Item, Place, Placeable


@entity
@dataclass
class Passage(GameObj, Placeable):
    """A passage from place to another.

    A single passage can only be entered from the room it is placed to.
    If bidirectional movement is needed, both rooms should get a passage.
    """
    target: Foreign[Place]


@dataclass
class CachedPlace:
    """In-memory cache of place."""
    place: Place
    passages: Dict[str, Passage]
    characters: List[CachedCharacter]
    items: List[Item]
