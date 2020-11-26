"""Places in the world."""

import asyncio
from dataclasses import dataclass, field
from enum import Flag, auto
import time
from typing import List, Set
from weakref import ReferenceType, ref

from loguru import logger

from tinymud.entity import Foreign, Entity, entity
from .character import Character
from .gameobj import GameObj, Placeable
from .item import Item


@dataclass
class _CachedPlace:
    """Cached data of a place.

    Reference to this should only permanently kept by the Place itself.
    This prevents the cached information from leaking when the Place is
    unloaded by GC.
    """
    characters: Set[Character]


class ChangeFlags(Flag):
    """Changes at a place during one tick.

    Change places are set when something (description, characters, items, etc.)
    changes in a place. They're cleared at end of place ticks, and can be used
    in on_tick handlers to e.g. decide which updates to send to clients.
    """
    DETAILS = auto()
    PASSAGES = auto()
    CHARACTERS = auto()
    ITEMS = auto()


@entity
@dataclass
class Place(Entity):
    """A place in the world.

    Each place has an unique address (str) in addition to numeric. The
    addresses are used mostly in content creation tools. Players are usually
    shown titles instead of place addresses, but both should be considered
    public knowledge.

    Header text is in markdown-like format (TODO) that is rendered to
    HTML by client.
    """
    address: str
    title: str
    header: str

    _cache: _CachedPlace = field(init=False)
    _changes: ChangeFlags = ChangeFlags(0)

    def __post_init__(self) -> None:
        # Create cache of this place
        characters = Character.select(Character.c().place == self.id)
        self._cache = _CachedPlace(characters)
        _new_places.append(ref(self))  # Add to be ticked

    async def passages(self) -> List['Passage']:
        return await Passage.select_many(Passage.c().place == self.id)

    async def items(self) -> List[Item]:
        return await Item.select_many(Item.c().place == self.id)

    def characters(self) -> Set[Character]:
        return self._cache.characters

    async def on_tick(self, delta: float) -> None:
        """Called when this place is ticked.

        The delta is time difference between start of current and previous
        place ticks, in seconds. This is NOT necessarily same as time between
        this and previous tick (that may or may not have even occurred).
        """
        # Swap change flags to none, so new changes won't take effect mid-tick
        # (and will be present in self._changes for next tick)
        changes = self._changes
        self._changes = ChangeFlags(0)

        # Call tick handler on all characters
        for character in self.characters():
            await character.on_tick(delta, changes)

    async def on_character_enter(self, character: Character) -> None:
        """Called when an character enters this place."""
        self._cache.characters.add(character)
        self._changes |= ChangeFlags.CHARACTERS

    def on_character_exit(self, character: Character) -> None:
        """Called when an character exists this place."""
        self._cache.characters.remove(character)
        self._changes |= ChangeFlags.CHARACTERS


@entity
class Passage(GameObj, Placeable):
    """A passage from place to another.

    A single passage can only be entered from the room it is placed to.
    If bidirectional movement is needed, both rooms should get a passage.
    """
    target: Foreign[Place]

    async def enter(self, character: Character) -> None:
        """Makes given character enter this passage."""
        if character.place != self.id:
            raise ValueError(f"character id {character.id} is not in place {self.address}")
        character.on_move(await Place.get(character.place), await Place.get(self.target))
        character.place = self.target


# Places that are currently pending addition to _places
_new_places: List[ReferenceType[Place]] = []

# Places that are currently ticked over
_places: List[ReferenceType[Place]] = []


async def _places_tick(delta: float) -> None:
    """Runs one tick over all places."""
    global _new_places
    global _places
    next_places = _new_places  # Places after this tick
    _new_places = []  # Places that get loaded/added during this tick

    # Process newly added places to avoid 1 tick delay
    for place_ref in _new_places:
        place = place_ref()
        if place:
            await place.on_tick(delta)
        # But we can't remove in place, so let it stay in _new_places

    # Iterate over current places
    for place_ref in _places:
        place = place_ref()
        if place:  # Not GC'd
            await place.on_tick(delta)
            next_places.append(place_ref)

    # Swap to places that still exist (and newly added ones)
    _places = _new_places  # And previous _places is deleted


async def _places_tick_loop(delta_target: float) -> None:
    prev_start = time.monotonic()
    await _places_tick(delta_target)  # First tick is always on time

    # Tick and wait if it didn't consume all time given
    while True:
        start = time.monotonic()
        delta = start - prev_start
        deviation = delta_target - delta
        if deviation > 0:  # We're early, need to wait
            await asyncio.sleep(deviation)
        else:  # (almost) failed to keep up?
            pass  # TODO logging every once a while (not EVERY tick)

        await _places_tick(delta)
        prev_start = start


async def start_places_tick(delta_target: float) -> None:
    """Starts places tick as background task."""
    asyncio.create_task(_places_tick_loop(delta_target))
    logger.info(f"Ticking loaded places every {delta_target} seconds")
