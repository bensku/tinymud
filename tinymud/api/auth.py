"""REST API for authentication etc."""

import secrets
import time
from typing import TypedDict

from aiohttp.web import Application, Request, Response, RouteTableDef
import jwt
from loguru import logger
from pydantic import BaseModel

from tinymud.world.user import RegistrationFailed, UserRoles, create_user, validate_credentials

auth_app = Application()
routes = RouteTableDef()

_jwt_secret: bytes = secrets.token_bytes(64)


class AuthToken(TypedDict):
    """Authentication token, passed around as JWT."""
    user_id: int
    exp: int


class LoginRequest(BaseModel):
    name: str
    password: str


def create_token(user_id: int) -> AuthToken:
    """Creates a new authentication token.

    The token is valid for a while, and its validity starts now.
    """
    valid_until = int(time.time()) + 2 * 3600  # 2 hours - TODO configurable token lifetime
    return {'user_id': user_id, 'exp': valid_until}


@routes.post('/login')
async def login(request: Request) -> Response:
    details = LoginRequest(**await request.json())
    # Will throw if credentials are not valid
    user = await validate_credentials(details.name, details.password)
    token = create_token(user.id)
    return Response(body=jwt.encode(token, _jwt_secret, 'HS256'))


@routes.post('/register')
async def register(request: Request) -> Response:
    # Will raise error if user cannot be created
    details = LoginRequest(**await request.json())
    if len(details.name) > 12:
        return Response(body="too long username", status=400)
    if len(details.password) > 100:
        return Response(body="too long password", status=400)

    try:
        user = await create_user(details.name, details.password)
        # FIXME something more secure than making first user admin
        if user.id == 1:
            logger.warning(f"First user '{user.name}'' created, making them an admin")
            user.roles = UserRoles.PLAYER | UserRoles.EDITOR
    except RegistrationFailed as e:
        return Response(body=str(e), status=409)
    logger.debug(f"User '{user.name}' registered")
    return Response()


@routes.post('/renew')
async def renew(request: Request) -> Response:
    # Won't renew unless it is actually valid
    old_token = validate_token(await request.json())
    new_token = create_token(old_token['user_id'])  # Same user, new expiration time
    return Response(body=jwt.encode(new_token, _jwt_secret, 'HS256'))


def validate_token(token: str) -> AuthToken:
    """Validates a JWT token.

    Raises something (TODO document what) if the token should not be accepted.
    """
    return jwt.decode(token, _jwt_secret, algorithms=['HS256'])  # type: ignore


auth_app.add_routes(routes)
