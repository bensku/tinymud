"""Player characters, monsters and others."""

from typing import Dict

from .gameobj import Character
from .item import Item


class CachedCharacter:
    """Common character information cached in memory."""
    char: Character
    inventory: Dict[str, Item]


# TODO NPC type registration (like item types)
