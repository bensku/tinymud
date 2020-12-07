"""Places in the world."""

import asyncio
from dataclasses import dataclass, field
from enum import Flag, auto
import time
from typing import Dict, List, Optional, ValuesView
from weakref import ReferenceType, ref

from loguru import logger
from pydantic import BaseModel

from tinymud.db import Foreign, Entity, entity, execute, fetch
from .character import Character
from .gameobj import Placeable
from .item import Item


@dataclass
class _CachedPlace:
    """Cached data of a place.

    Reference to this should only permanently kept by the Place itself.
    This prevents the cached information from leaking when the Place is
    unloaded by GC.
    """
    characters: Dict[int, Character]
    passages: Dict[str, 'Passage']


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
    _cache_done: bool = False
    _changes: ChangeFlags = ChangeFlags(0)

    @staticmethod
    async def from_addr(address: str) -> Optional['Place']:
        """Gets a place based on its unique address."""
        return await Place.select(Place.c().address == address)

    def __object_created__(self) -> None:
        _new_places.append(ref(self))  # Add to be ticked

    async def make_cache(self) -> None:
        if self._cache_done:
            return  # Cache already created

        # Load all characters (by their ids)
        characters = {}
        for character in await Character.select_many(Character.c().place == self.id):
            characters[character.id] = character

        # Load all passages (by their target addresses)
        # Avoid unnecessary queries later by doing unnecessarily complex query tricks
        # Totally not premature optimization (hmm)
        passages = {}
        for record in await fetch(('SELECT passage.id id, passage.place as place, passage.name as name, passage.target target,'
                ' passage.hidden hidden, place.address _address, place.title _place_title'
                f' FROM {Passage._t} passage JOIN {Place._t} place'
                ' ON target = place.id WHERE passage.place = $1'), self.id):
            passage = Passage.from_record(record)
            passage._cache_done = True  # We provided extra values in constructor
            passages[passage._address] = passage

        self._cache = _CachedPlace(characters, passages)
        self._cache_done = True

    async def passages(self) -> ValuesView['Passage']:
        await self.make_cache()
        return self._cache.passages.values()

    async def items(self) -> List[Item]:
        return await Item.select_many(Item.c().place == self.id)

    async def characters(self) -> ValuesView[Character]:
        await self.make_cache()
        return self._cache.characters.values()

    async def update_passages(self, passages: List['PassageData']) -> None:
        """Updates passages leaving from this place."""
        await self.make_cache()
        # Delete previous passages
        await execute(f'DELETE FROM {Passage._t} WHERE id = $1', [self.id])
        self._cache.passages = {}

        # Create new passages
        for passage in passages:
            target = await Place.from_addr(passage.address)
            if not target:
                logger.warning(f"Passage to missing place {passage.address}")
                continue  # Missing passage, TODO user feedback
            entity = Passage(self.id, target.id, passage.name, passage.hidden,
                _cache_done=True, _address=passage.address, _place_title=target.title)
            self._cache.passages[target.address] = entity

        # Update to clients
        self._changes |= ChangeFlags.PASSAGES

    async def use_passage(self, character: Character, address: str) -> None:
        await self.make_cache()
        if address not in self._cache.passages:
            raise ValueError(f'no passage from {self.address} to {address}')
        to_place = await Place.get(self._cache.passages[address].target)
        await character.move(to_place)

    async def on_tick(self, delta: float) -> None:
        """Called when this place is ticked.

        The delta is time difference between start of current and previous
        place ticks, in seconds. This is NOT necessarily same as time between
        this and previous tick (that may or may not have even occurred).
        """
        await self.make_cache()
        # Swap change flags to none, so new changes won't take effect mid-tick
        # (and will be present in self._changes for next tick)
        changes = self._changes
        self._changes = ChangeFlags(0)

        # Call tick handler on all characters
        for character in await self.characters():
            await character.on_tick(delta, changes)

    async def on_character_enter(self, character: Character) -> None:
        """Called when an character enters this place."""
        await self.make_cache()
        self._cache.characters[character.id] = character
        self._changes |= ChangeFlags.CHARACTERS

    async def on_character_exit(self, character: Character) -> None:
        """Called when an character exists this place."""
        await self.make_cache()
        del self._cache.characters[character.id]
        self._changes |= ChangeFlags.CHARACTERS


class PassageData(BaseModel):
    """Passage data sent by client."""
    address: str
    name: Optional[str]
    hidden: bool


@entity
@dataclass
class Passage(Placeable, Entity):
    """A passage from place to another.

    A single passage can only be entered from the room it is placed to.
    If bidirectional movement is needed, both rooms should get a passage.

    Passages can be named, but by default they inherit names of their targets.
    Note that text shown inside place header is usually different. For
    passages hidden from exit list, names are never shown to players.
    """
    target: Foreign[Place]
    name: Optional[str]
    hidden: bool

    # Some cached data from other places
    # Note that usually place caching queries them with one SELECT
    _cache_done: bool = False
    _address: str = ''  # Target address (client deals with addresses, not place ids)
    _place_title: str = ''

    async def _make_cache(self) -> None:
        if self._cache_done:
            return  # Already cached
        place = await Place.get(self.target)
        self._address = place.address
        self._place_title = place.title
        self._cache_done = True

    async def address(self) -> str:
        await self._make_cache()
        return self._address

    async def place_title(self) -> str:
        await self._make_cache()
        return self._place_title

    async def client_data(self) -> PassageData:
        await self._make_cache()
        return PassageData(address=self._address, name=self.name, hidden=self.hidden)


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
    for place_ref in next_places:
        place = place_ref()
        if place:
            await place.on_tick(delta)
        # But we can't remove in place, so let it stay in _new_places

    # Iterate over current places
    for place_ref in _places:
        place = place_ref()
        if place and not place._destroyed:  # Not GC'd, not destroyed
            await place.on_tick(delta)
            _new_places.append(place_ref)

    # Swap to places that still exist (and newly added ones)
    _places = next_places  # And previous _places is deleted


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


_limbo_place: Place


async def init_limbo_place() -> None:
    """Initializes the 'default' place, Limbo.

    Limbo is used (hopefully) only during development, when other places
    don't exist in the database.
    """
    limbo = await Place.from_addr('tinymud.limbo')
    if not limbo:
        logger.debug("Creating limbo place (empty database?)")
        limbo = Place(
            address='tinymud.limbo',
            title="Limbo",
            header="Nothing to see here."
        )
    global _limbo_place
    _limbo_place = limbo
