"""Client served for development purposes."""

from pathlib import Path

from aiohttp.web import FileResponse, Request, RouteTableDef

routes = RouteTableDef()

client_path = Path('client')
assets_path = client_path / 'assets'


@routes.get('/')
async def get_index(request: Request) -> FileResponse:
    return FileResponse(assets_path / 'pages' / 'index.html')


routes.static('/app', client_path / 'dist' / 'app')
routes.static('/pages', assets_path / 'pages')
routes.static('/styles', assets_path / 'styles')
routes.static('/vendor', client_path / 'dist' / 'vendor')


dev_routes = routes
