"""REST API for authentication etc."""

import secrets

from aiohttp.web import Application, Request, Response, RouteTableDef
import jwt
from pydantic import BaseModel

from tinymud.world.user import validate_credentials

auth_app = Application()
routes = RouteTableDef()

_jwt_secret: bytes = secrets.token_bytes(64)


class LoginRequest(BaseModel):
    name: str
    password: str


@routes.post('/login')
async def login(request: Request):
    details = LoginRequest(**await request.json())
    # Will throw if credentials are not valid
    user = await validate_credentials(details.name, details.password)
    return Response(body=jwt.encode({'user': user.name}, _jwt_secret, 'HS256'))


auth_app.add_routes(routes)
