"""Tinymud main application."""

import asyncio
import importlib.util
from pathlib import Path
import sys

import asyncpg
from loguru import logger

from tinymud.api.app import run_app
from tinymud.db.entity import init_entity_system

from tinymud.world.gameobj import init_obj_system
from tinymud.world.place import init_limbo_place, start_places_tick
from tinymud.world.user import enable_test_login


async def start(db_url: str, game_path: Path, prod_mode: bool, update_schema: bool, save_interval: int,
        host: str, port: int, test_login: bool) -> None:
    # Wait until database is up
    # This is especially relevant for development Docker database
    while True:
        try:
            conn = await asyncpg.connect(db_url)
            await conn.close()
            break
        except asyncpg.exceptions.ConnectionDoesNotExistError:
            logger.info("Waiting for database...")
            await asyncio.sleep(2)

    # Start entity system
    conn_pool = await asyncpg.create_pool(db_url)
    logger.info("Connected to database, starting entity system")
    await init_entity_system(conn_pool, Path('db_data').absolute(), prod_mode, update_schema, save_interval)

    # Load game from given path before starting any more systems
    load_game(game_path)
    logger.info(f"Loaded game '{game_path.name}'")

    await init_obj_system()
    await init_limbo_place()
    await start_places_tick(0.2)  # TODO configurable tick rate

    # If test login was enabled, disable authentication
    if test_login:
        enable_test_login()

    # Run Sanic-based web application
    await run_app(host, port)
    logger.info(f"Tinymud listening at {host}:{port}")


def load_game(path: Path) -> None:
    """Loads the game module from given path."""
    spec = importlib.util.spec_from_file_location(path.name, path / '__init__.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    # Missing types, we're probably doing something a bit hacky here...
    spec.loader.exec_module(module)  # type: ignore
