"""Tinymud main application."""

import asyncio
from pathlib import Path

import asyncpg
from loguru import logger

from tinymud.api.app import run_app
from tinymud.db.entity import init_entity_system

from tinymud.world.gameobj import init_obj_system


async def start(db_url: str, game_path: Path, prod_mode: bool, save_interval: int,
        host: str, port: int) -> None:
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
    await init_entity_system(conn_pool, Path('db_data').absolute(), prod_mode, save_interval)
    logger.info("Entity system initialized")

    await init_obj_system()
    logger.info("Game object system initialized")

    # Run Sanic-based web application
    await run_app(host, port)
    logger.info(f"Tinymud listening at {host}:{port}")
