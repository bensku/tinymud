"""Tinymud main application."""

import asyncio
from pathlib import Path

import asyncpg

from tinymud.db.entity import init_entity_system

# conn_pool: Pool = await create_pool(database)


async def start(db_url: str, game_path: Path):
    # Wait until database is up
    # This is especially relevant for development Docker database
    while True:
        try:
            conn = await asyncpg.connect(db_url)
            await conn.close()
            break
        except asyncpg.exceptions.ConnectionDoesNotExistError:
            print("Waiting for database...")
            await asyncio.sleep(3)

    conn_pool = await asyncpg.create_pool(db_url)
    # TODO get prod mode flag and save interval from launcher
    await init_entity_system(conn_pool, Path('db_data').absolute(), False, 30)
