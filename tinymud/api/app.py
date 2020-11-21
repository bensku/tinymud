"""Sanic web application main."""

from aiohttp.web import Application, AppRunner, Request, Response, RouteTableDef, TCPSite

from .auth import auth_app
from .game import game_app

app = Application()
app.add_subapp('/auth/', auth_app)
app.add_subapp('/game/', game_app)

routes = RouteTableDef()


@routes.get('/status')
async def get_status(request: Request) -> Response:
    return Response(text="OK")


app.add_routes(routes)


async def run_app(host: str, port: int) -> None:
    runner = AppRunner(app)
    await runner.setup()
    site = TCPSite(runner, host, port)
    await site.start()
