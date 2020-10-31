
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Type, Set, TypeVar, get_type_hints

from asyncpg import Connection, Record
from asyncpg.pool import Pool

from .migration import TableMigrator
import tinymud.db.schema as schema
from .schema import TableSchema

# Connection that can be used for one-shot operations
# Don't ever use this for transactions!
_entity_conn: Connection


T = TypeVar('T', bound='Entity')


class Entity:
    """Base type of all entities."""
    id: int
    _next_id: int

    # Table schema and SQL queries
    _schema: TableSchema
    _sql_create_table: str
    _sql_insert: str
    _sql_select: str
    _sql_update: str
    _sql_delete: str

    @classmethod
    async def get(cls: Type[T], id: int) -> T:
        """Gets an entity by id."""
        query = cls._sql_select + ' WHERE id = $1'
        return _record_to_obj(cls, await _entity_conn.fetchrow(query, id))


def _record_to_obj(py_type: Type[T], record: Record) -> T:
    """Converts a database record (row) to entity of given type."""
    # Pass all values (including id) to constructor as named arguments
    obj = py_type(**record.values())  # type: ignore
    return obj


def _obj_to_values(obj: Entity, table: TableSchema) -> list:
    """Gets fields of an entity to as list"""
    values = []
    for column in table['columns']:
        values.append(getattr(obj, column['name']))
    return values


def entity(entity_type: Type[T]) -> Type[T]:
    # Patch init to set id and queue for _new_entities as needed
    old_init = entity_type.__init__

    def new_init(self: T, **kwargs):
        if 'id' in kwargs:  # Loaded from database
            self.id = kwargs['id']
            del kwargs['id']
        else:  # Actually created a new entity
            # Take next id
            entity_type._next_id += 1
            self.id = entity_type._next_id
            _new_entities.add(self)  # Queue to be saved

        # Call old init to actually set fields
        # Also raises exceptions if there are extra values
        old_init(self, **kwargs)  # type: ignore
    setattr(entity_type, '__init__', new_init)

    # Figure out fields and create table schema based on them
    fields: Dict[str, Type] = {}
    for component in entity_type.mro():
        if component == object:
            continue  # Doesn't have anything interesting for us
        for name, field_type in get_type_hints(component).items():
            if name in fields:
                pass  # TODO error
            fields[name] = field_type
    table = schema.new_table_schema('tinymud_' + entity_type.__name__.lower(), fields)
    entity_type._schema = table

    # Figure out CREATE TABLE, INSERT, SELECT, UPDATE and DELETE
    entity_type._sql_create_table = schema.get_create_table(table)
    entity_type._sql_insert = schema.get_sql_insert(table)
    entity_type._sql_select = schema.get_sql_select(table['name'])
    entity_type._sql_update = schema.get_sql_update(table)
    entity_type._sql_delete = schema.get_sql_delete(table['name'])

    # Patch in change detection for fields
    def mark_changed(self: T, key: str, value: str) -> None:
        # Queue to be saved and prevent GC before that happens
        _changed_entities.add(self)
    setattr(entity_type, '__setattr__', mark_changed)

    # Queue for async init
    _async_init_needed.add(entity_type)

    return entity_type


# Newly created and changed entities that need to be saved to DB
_new_entities: Set[Entity] = set()
_changed_entities: Set[Entity] = set()


async def save_entities(conn: Connection) -> None:
    """Saves changed and newly created entities to DB."""
    async with conn.transaction():
        # INSERT newly created entities
        for entity in _new_entities:
            entity_type = type(entity)
            await conn.execute(entity_type._sql_insert, _obj_to_values(entity, entity_type._schema))

        # UPDATE changed entities
        for entity in _changed_entities:
            entity_type = type(entity)
            await conn.execute(entity_type._sql_update, _obj_to_values(entity, entity_type._schema))

# Classes decorated with entity need some data injected from async DB callbacks
_async_init_needed: Set[Type[Entity]] = set()


async def _async_init_entities(conn: Connection, db_data: Path, prod_mode: bool):
    """Performs late/async initialization on entities."""
    migrator = TableMigrator(conn, db_data, prod_mode)
    await migrator.create_sys_tables()
    for entity_type in _async_init_needed:
        # Ensure that the DB table exists and matches Python class
        table_schema = entity_type._schema
        await migrator.migrate_table(table_schema)

        # Figure out and inject next free id
        entity_type._next_id = await conn.fetchval(f'SELECT COUNT(*) FROM {table_schema["name"]}')


async def _save_entities_timer(conn_pool: Pool, interval: float) -> None:
    """Periodically saves entities."""
    while True:
        async with conn_pool.acquire() as conn:
            await save_entities(conn)
        await asyncio.sleep(interval)


async def init_entity_system(conn_pool: Pool, db_data: Path, prod_mode: bool, save_interval: float) -> None:
    # Reserve connection for 'one-shot' operations
    global _entity_conn
    _entity_conn = conn_pool.acquire()

    # Perform async initialization as needed for entities
    async with conn_pool.acquire() as conn:
        async with conn.transaction():  # Either all migrations work, or none do
            await _async_init_entities(conn, db_data, prod_mode)
    _async_init_needed.clear()

    # Periodically save newly created and modified entities
    asyncio.get_event_loop().call_later(save_interval, _save_entities_timer)


@entity
@dataclass
class GameObj(Entity):
    foo: str
