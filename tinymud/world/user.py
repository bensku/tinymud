"""User management."""

from dataclasses import dataclass
from typing import List

import argon2
from loguru import logger

from tinymud.entity import Entity, entity
from .character import Character


@entity
@dataclass
class User(Entity):
    """Tinymud user.

    Each user may have one or more player characters, that is, characters
    they're allowed to play. Privileged users might also be able to control
    other characters.
    """
    name: str
    password_hash: str  # argon2 hash, not cleartext password!

    @property
    async def owned_characters(self) -> List[Character]:
        return await Character.select_many(Character.c().owner == self.id)


class InvalidCredentials(Exception):
    """Raised when credentials didn't match."""


_hasher = argon2.PasswordHasher()
_test_login = False


async def validate_credentials(name: str, password: str) -> User:
    """Validates credentials.

    If an user with given name and password exists, it is returned.
    Otherwise, a InvalidCredentials error is raised.
    """
    user = await User.select(User.c().name == name)
    if not user:
        if _test_login:  # Just create an user!
            logger.info(f"Creating user {name} for test login")
            user = User(name, _hasher.hash(password))
        else:  # This is an error
            raise InvalidCredentials()

    if _test_login:
        logger.warning(f"Skipping authentication for user {name}")
        return user

    # Found user, check if passwords match
    try:
        _hasher.verify(user.password_hash, password)
    except:  # noqa: E722
        # No matter why it failed, can't allow login
        # TODO log 'unusual' failures (e.g. invalid hashes in DB)
        raise InvalidCredentials()

    return user  # Everything passed, give caller the user


def enable_test_login() -> None:
    """Enables test logins.

    This DISABLES authentication. Only ever use it in local development.
    """
    logger.warning("Authentication is disabled (--test-login)")
    global _test_login
    _test_login = True
