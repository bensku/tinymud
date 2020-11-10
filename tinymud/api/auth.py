"""REST API for authentication etc."""

import secrets
from typing import TypedDict

from aiohttp.web import Application, Request, Response, RouteTableDef
import jwt
from pydantic import BaseModel

from tinymud.world.user import validate_credentials

auth_app = Application()
routes = RouteTableDef()

_jwt_secret: bytes = secrets.token_bytes(64)


class AuthToken(TypedDict):
    """Authentication token, passed around as JWT."""
    user_id: int


class LoginRequest(BaseModel):
    name: str
    password: str


@routes.post('/login')
async def login(request: Request):
    details = LoginRequest(**await request.json())
    # Will throw if credentials are not valid
    user = await validate_credentials(details.name, details.password)
    token: AuthToken = {'user_id': user.id}
    return Response(body=jwt.encode(token, _jwt_secret, 'HS256'))


def validate_token(token: str) -> AuthToken:
    return jwt.decode(token, _jwt_secret)  # type: ignore


auth_app.add_routes(routes)
