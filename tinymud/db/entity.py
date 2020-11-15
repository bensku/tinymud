
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Type, Set, TypeVar, get_type_hints
from weakref import WeakValueDictionary

from asyncpg import Connection, Record
from asyncpg.pool import Pool
from loguru import logger

from .migration import TableMigrator
import tinymud.db.schema as schema
from .schema import TableSchema

# Global connection pool; prefer _entity_conn for short operations
_conn_pool: Pool

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
    _sql_insert: str
    _sql_select: str
    _sql_update: str
    _sql_delete: str

    # 'Entity' with attributes to support query DSL
    _field_names: object

    # Cache to avoid querying out-of-date entities from database
    # As long as change queue (or some other cache) holds the entity,
    # this will keep it too
    _cache: WeakValueDictionary

    @classmethod
    async def get(cls: Type[T], id: int) -> Optional[T]:
        """Gets an entity by id."""
        cache: WeakValueDictionary = cls._cache
        if id in cache:  # Check if our cache has it
            return cache[id]
        query = cls._sql_select + ' WHERE id = $1'
        record = await _entity_conn.fetchrow(query, id)
        return _record_to_obj(cls, record) if record else None

    @classmethod
    def c(cls: Type[T]) -> T:
        return cls._field_names  # type: ignore

    @classmethod
    async def select_many(cls: Type[T], *args) -> List[T]:
        # Generate WHERE clauses and associate values with them
        clauses = []
        values = []
        for arg in args:
            (entity, field, value, sql_op) = arg
            if cls != entity:
                raise ValueError('tried to select(...) with fields from different entity')
            # field and sql_op are trusted; they never come in as user input
            # They're not even provided to us directly as strings
            values.append(value)
            clauses.append(f'{field} {sql_op} ${len(values)}')

        query = entity._sql_select + ' WHERE ' + ' AND '.join(clauses)

        # Query all matching from database
        # Replace some records with entities from cache
        # (DB may have entities missing from cache, so we need to query them anyway)
        async with _conn_pool.acquire() as conn:
            cache: WeakValueDictionary = cls._cache
            entities = []
            for record in conn.fetch(query, *values):
                entity_id = record[0]
                if entity_id in cache:  # Use cached entity if possible
                    entities.append(cache[entity_id])
                else:  # Not found, actually convert record to entity
                    entity = _record_to_obj(cls, record)
                    entities.append(entity)
            return entities

    @classmethod
    async def select(cls: Type[T], *args) -> Optional[T]:
        # TODO add own implementation, select_many() CAN be very slow
        results = await cls.select_many(*args)
        return results[0] if len(results) > 0 else None


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


class OverloadedField:
    """Field with overloaded comparison methods.

    All comparisons return tuple of
    (entity type, field name, value to compare against, sql operator)
    """
    def __init__(self, entity: Type[Entity], field: str):
        self.entity = entity
        self.field = field

    def __lt__(self, other):
        return self.entity, self.field, other, '<'

    def __le__(self, other):
        return self.entity, self.field, other, '<='

    def __eq__(self, other):
        return self.entity, self.field, other, '='

    def __ne__(self, other):
        return self.entity, self.field, other, '!='

    def __gt__(self, other):
        return self.entity, self.field, other, '>'

    def __ge__(self, other):
        return self.entity, self.field, other, '>='


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

        # Cache this entity to its type (weakly referenced)
        entity_type._cache[self.id] = self
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
    table = schema.new_table_schema(schema.new_table_name(entity_type), fields)
    entity_type._schema = table

    # Figure out CREATE TABLE, INSERT, SELECT, UPDATE and DELETE
    entity_type._sql_insert = schema.get_sql_insert(table)
    entity_type._sql_select = schema.get_sql_select(table['name'])
    entity_type._sql_update = schema.get_sql_update(table)
    entity_type._sql_delete = schema.get_sql_delete(table['name'])

    # Populate field names used for query DSL (select and friends)
    field_names: List[OverloadedField] = []
    for name in fields.keys():
        field_names.append(OverloadedField(entity_type, name))
    entity_type._field_names = field_names

    # Patch in change detection for fields
    def mark_changed(self: T, key: str, value: str) -> None:
        # Queue to be saved and prevent GC before that happens
        _changed_entities.add(self)
    setattr(entity_type, '__setattr__', mark_changed)

    # Create entity cache for this type
    entity_type._cache = WeakValueDictionary()

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
    logger.info("Initializing entity types...")
    migrator = TableMigrator(conn, db_data, prod_mode)
    await migrator.create_sys_tables()

    # Queue tables to be created, migrated etc.
    for entity_type in _async_init_needed:
        await migrator.add_table(entity_type._schema)

    # Create and migrate tables (+ their post create triggers)
    created_count = await migrator.create_tables()
    if created_count > 0:
        logger.info(f"Created {created_count} tables")
    migrated_count = await migrator.migrate_tables()
    if migrated_count > 0:
        logger.info(f"Migrated {migrated_count} existing tables")
    post_count = await migrator.exec_post_create()
    if post_count > 0:
        logger.info(f"Executed {post_count} post create statements")

    logger.debug(f"Found {len(_async_init_needed)} entity types")

    # Figure out and assign next free ids
    for entity_type in _async_init_needed:
        table_schema = entity_type._schema
        current_id = await conn.fetchval(f'SELECT max(id) FROM {table_schema["name"]}')
        entity_type._next_id = current_id + 1 if current_id else 0


async def _save_entities_timer(interval: float) -> None:
    """Periodically saves entities."""
    while True:
        await asyncio.sleep(interval)
        async with _conn_pool.acquire() as conn:
            await save_entities(conn)


async def init_entity_system(conn_pool: Pool, db_data: Path, prod_mode: bool, save_interval: float) -> None:
    # Reserve connection for 'one-shot' operations
    global _entity_conn
    _entity_conn = conn_pool.acquire()

    # Also make the pool available for... longer operations
    global _conn_pool
    _conn_pool = conn_pool

    # Perform async initialization as needed for entities
    async with conn_pool.acquire() as conn:
        async with conn.transaction():  # Either all migrations work, or none do
            await _async_init_entities(conn, db_data, prod_mode)
    _async_init_needed.clear()

    # Periodically save newly created and modified entities
    asyncio.create_task(_save_entities_timer(save_interval))
