"""Game-related APIs (mostly Websocket)."""

from aiohttp.web import Application, Request, RouteTableDef, WebSocketResponse, WSMsgType

from loguru import logger

from .message import ClientConfig, handle_client_msg
from .session import Session, create_character
from tinymud.api.auth import validate_token
from tinymud.world import Character, User

game_app = Application()
routes = RouteTableDef()


@routes.get('/ws')
async def game_ws(request: Request) -> WebSocketResponse:
    ws = WebSocketResponse()
    await ws.prepare(request)

    # Wait for client to send JWT auth token
    auth_token = validate_token((await ws.receive()).data)
    user = await User.get(auth_token['user_id'])
    session = Session(user, ws)
    logger.debug(f"User '{user.name}' connected (WebSocket)")

    # Send configuration (currently, user roles) to client
    # It will know not to e.g. render admin features to normal users
    # (though obviously we check all API calls here in backend, too)
    config = ClientConfig(roles=user.roles)
    await session.send_msg(config)

    # TODO character select screen (full multi character support)
    character = await Character.select(Character.c().owner == user.id)
    if not character:
        character = await create_character(session)
    await session.set_character(character)  # Take control of the character

    # Receive messages and deal with them
    while True:
        # session.receive_msg() expects type, which we don't know
        msg = await ws.receive()
        if msg.type == WSMsgType.CLOSE:
            # Client dropped connection
            # TODO do something about it (remove character from world?)
            logger.debug(f"User '{user.name}' disconnected")
            return ws

        await handle_client_msg(session, msg.json())

    return ws


game_app.add_routes(routes)
