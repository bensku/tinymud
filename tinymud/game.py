"""Most commonly used game-facing APIs."""

from abc import ABC, abstractmethod
from typing import List

from tinymud.world.character import Character, CharacterTemplate
from tinymud.world.user import User
from tinymud.world.place import Place


class GameHooks(ABC):
    """Hooks that allow game to control Tinymud operations.

    All games must implement at least the @abstractmethod hooks, and may
    implement others (if available).
    """
    @abstractmethod
    async def get_character_options(self, user: User) -> List[CharacterTemplate]:
        """Gets character creation options for given user."""

    @abstractmethod
    async def get_starting_place(self, character: Character, user: User) -> Place:
        """Gets starting place for a newly created character."""


# Hooks for current game
# This is checked to be present after game __init__ returns
_game_hooks: GameHooks


def game_hooks() -> GameHooks:
    """Gets current game hooks."""
    return _game_hooks


def set_game_hooks(hooks: GameHooks) -> None:
    """Sets game hooks.

    This must be done exactly once before module __init__ of a game returns.
    """
    global _game_hooks
    _game_hooks = hooks
