"""Tinymud main application."""

from asyncpg import create_pool

from .db.entity import init_entity_system

#conn_pool: Pool = await create_pool(database)

init_entity_system()