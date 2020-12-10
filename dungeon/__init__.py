from typing import List

from tinymud.game import GameHooks, set_game_hooks
from tinymud.world.character import CharacterTemplate, CharacterType, Character, character
from tinymud.world.place import Place
from tinymud.world.user import User


@character('adventurer')
class Adventurer(CharacterType):
    """An adventurer."""


class DungeonHooks(GameHooks):
    async def get_character_options(self, user: User) -> List[CharacterTemplate]:
        return [
            CharacterTemplate(Adventurer, "An adventurer", [])
        ]

    async def get_starting_place(self, character: Character, user: User) -> Place:
        return await Place.from_addr('tinymud.limbo')


set_game_hooks(DungeonHooks())
