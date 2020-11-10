"""User management."""

import argon2

from tinymud.db.entity import Entity, entity


@entity
class User(Entity):
    """Tinymud user.

    Each user may have one or more player characters, that is, characters
    they're allowed to play. Privileged users might also be able to control
    other characters.
    """
    name: str
    password_hash: str  # argon2 hash, not cleartext password!


class InvalidCredentials(Exception):
    """Raised when credentials didn't match."""


_hasher = argon2.PasswordHasher()


async def validate_credentials(name: str, password: str) -> User:
    """Validates credentials.

    If an user with given name and password exists, it is returned.
    Otherwise, a InvalidCredentials error is raised.
    """
    user = await User.select(User.c().name == name)
    if not user:
        raise InvalidCredentials()

    # Found user, check if passwords match
    try:
        _hasher.verify(user.password_hash, password)
    except:  # noqa: E722
        # No matter why it failed, can't allow login
        # TODO log 'unusual' failures (e.g. invalid hashes in DB)
        raise InvalidCredentials()

    return user  # Everything passed, give caller the user
