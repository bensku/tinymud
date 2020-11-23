"""Client served for development purposes."""

from pathlib import Path

from aiohttp.web import FileResponse, Request, RouteTableDef

routes = RouteTableDef()

client_path = Path('client')
assets_path = client_path / 'assets'


@routes.get('/')
async def get_index(request: Request) -> FileResponse:
    return FileResponse(assets_path / 'pages' / 'index.html')


@routes.get('/app.js')
async def get_app(request: Request) -> FileResponse:
    return FileResponse(client_path / 'dist' / 'app.js')


routes.static('/app', client_path / 'dist' / 'app')
routes.static('/pages', assets_path / 'pages')
routes.static('/styles', assets_path / 'styles')
routes.static('/vendor', client_path / 'dist' / 'vendor')


dev_routes = routes
