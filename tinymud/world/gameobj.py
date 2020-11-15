"""Core game object types."""

from dataclasses import dataclass
import inspect
from typing import Dict, List, Optional, Tuple, Type

from tinymud.entity import Entity, Foreign, entity
from .user import User


@dataclass
class ObjType:
    """Game object type.

    All types have both (unique) internal name and user-facing name.
    They may also have a longer description ("lore") that is shown (TODO when?).
    """
    id_str: str
    name: str
    lore: Optional[str]
    # TODO add some event handler methods that can be overridden etc.


_obj_types: Dict[int, ObjType] = {}  # Lookup table for ids in database
_register_queue: List[ObjType] = []  # Queue for async GameObj type registrations


@entity
@dataclass
class _TypeMapping(Entity):
    """Persistent GameObj type mappings.

    Object type names are mapped to numeric ids, and those mappings are
    persisted to same database where they are used.
    """
    id_str: str


def _register_obj_type(type: ObjType) -> None:
    """Queues a game object type registration.

    Registrations are queued because (async) database calls are needed
    for getting numeric ids. We can't do that from a decorator.
    """
    _register_queue.append(type)


def _docstring_extract(type: Type[ObjType]) -> Tuple[str, Optional[str]]:
    """Extracts name and lore (if present) from docstring."""
    # inspect.getdoc() searches from inheritance hierarchy
    # While ObjType hierarchy definitely has no secrets, having an item
    # named "Game object type" is not nice. We'll raise an error instead.
    docstring = type.__doc__
    if not docstring:
        raise ValueError(f'missing name (docstring) for {type}')
    docstring = inspect.cleandoc(docstring)

    lines = docstring.split('\n')
    if len(lines) == 1:
        return lines[0], None
    return lines[0], '\n'.join(lines[1:])


async def init_obj_system() -> None:
    """Initializes game object system."""
    for obj_type in _register_queue:
        record = await _TypeMapping.select(_TypeMapping.c().id_str == obj_type.id_str)
        if not record:  # New type, add to database table
            record = _TypeMapping(obj_type.id_str)
        _obj_types[record.id] = obj_type


@entity
@dataclass
class GameObj(Entity):
    """An object in the game world."""
    obj_type_id: int
    name: Optional[str]

    @property
    def type(self) -> ObjType:
        """Type of game object."""
        return _obj_types[self.obj_type_id]


@dataclass
class Placeable(Entity):
    place: Optional[Foreign['Place']]


@dataclass
class Carriable(Entity):
    owner: Optional[Foreign['Character']]


# Avoid circular imports by declaring certain core entity types


@entity
@dataclass
class Place(Entity):
    """A place in the world.

    Each place has an unique address (str) in addition to numeric. The
    addresses are used mostly in content creation tools. Players are usually
    shown titles instead of room addresses, but both should be considered
    public knowledge.

    Header text is in markdown-like format (TODO) that is rendered to
    HTML by client.
    """
    address: str
    title: str
    header: str


@entity
@dataclass
class Character(GameObj, Placeable):
    """A character in the world.

    A character owned by an user is considered to be a player character.
    All other characters are known as NPCs internally.
    """
    owner: Optional[Foreign[User]]