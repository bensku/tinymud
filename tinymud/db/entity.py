"""Tinymud entity system."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, Set, TypeVar, cast
from weakref import WeakValueDictionary

from asyncpg import Connection, Record
from asyncpg.pool import Pool
from loguru import logger

from .migration import TableMigrator
import tinymud.db.schema as schema
from .schema import TableSchema


# Global connection pool of entity system
# FIXME try to ensure data consistency on crash
# Simple transactions won't help, because we're using multiple connections
# Using one connections with a queue for ALL operations would be safer
# (but too complex to implement for now)
# Let's just hope it doesn't crash
_conn_pool: Pool


class _FieldNames:
    """Field names are setattr'd into instances of this."""


T = TypeVar('T', bound='Entity')


class Entity:
    """Base type of all entities."""
    id: int
    _next_id: int
    _destroyed: bool

    # Table schema and SQL queries
    _schema: TableSchema
    _sql_insert: str
    _sql_select: str
    _sql_update: str
    _sql_delete: str

    # 'Entity' with attributes to support query DSL
    _field_names: _FieldNames

    # Cache to avoid querying out-of-date entities from database
    # As long as change queue (or some other cache) holds the entity,
    # this will keep it too
    _entity_cache: WeakValueDictionary[int, 'Entity']

    async def __entity_created__(self) -> None:
        """Called when this entity is created in database.

        This may take a while (few seconds at most) after the object has been
        created. Note that being loaded from database doesn't qualify;
        if you want that, __post_init__ of dataclasses should do the trick.
        It also gets called immediately after constructor sychronously.
        """
        pass

    def __object_created__(self) -> None:
        """Called at end of constructor of entity type."""

    async def __entity_destroyed__(self) -> None:
        """Called immediately before this entity is destroyed.

        Note that only deletion from database counts as 'destruction' here.
        Use __del__ if you want to be called every time an entity is unloaded.
        """
        pass

    async def destroy(self) -> None:
        """Destroys this entity and all references to it.

        Attribute _destroyed is set to True to identify objects of destroyed
        entities. Future changes to them are not saved anywhere.
        """
        await self.__entity_destroyed__()
        self._destroyed = True
        async with _conn_pool.acquire() as conn:
            conn.execute(type(self)._sql_delete, self.id)

    @classmethod
    async def get(cls: Type[T], id: int) -> Optional[T]:
        """Gets an entity by id."""
        if id is None:
            raise ValueError('missing id')

        cache: WeakValueDictionary[int, Entity] = cls._entity_cache
        if id in cache:  # Check if our cache has it
            return cast(T, cache[id])
        query = cls._sql_select + ' WHERE id = $1'
        async with _conn_pool.acquire() as conn:
            record = await conn.fetchrow(query, id)
        return _record_to_obj(cls, record) if record else None

    @classmethod
    def c(cls: Type[T]) -> T:
        return cls._field_names  # type: ignore

    @classmethod
    async def select_many(cls: Type[T], *args: bool) -> List[T]:
        # args type is fake, FIXME if possible

        # Generate WHERE clauses and associate values with them
        clauses = []
        values = []
        for arg in args:
            entity: Type[Entity]
            field: str
            value: Any
            sql_op: str
            entity, field, value, sql_op = arg  # type: ignore
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
        cache: WeakValueDictionary[int, Entity] = cls._entity_cache
        entities = []
        async with _conn_pool.acquire() as conn:
            for record in await conn.fetch(query, *values):
                entity_id = record[0]
                if entity_id in cache:  # Use cached entity if possible
                    entities.append(cache[entity_id])
                else:  # Not found, actually convert record to entity
                    entities.append(_record_to_obj(cls, record))
        return cast(List[T], entities)

    @classmethod
    async def select(cls: Type[T], *args: bool) -> Optional[T]:
        # TODO add own implementation, select_many() CAN be very slow
        results = await cls.select_many(*args)
        return results[0] if len(results) > 0 else None


def _record_to_obj(py_type: Type[T], record: Record) -> T:
    """Converts a database record (row) to entity of given type."""
    # Pass all values (including id) to constructor as named arguments
    obj = py_type(**dict(record.items()))  # type: ignore
    return obj


def _obj_to_values(obj: Entity, table: TableSchema) -> List[Any]:
    """Gets fields of an entity to as list"""
    values = [obj.id]
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

    def __lt__(self, other: Any) -> Tuple[Type[Entity], str, Any, str]:
        return self.entity, self.field, other, '<'

    def __le__(self, other: Any) -> Tuple[Type[Entity], str, Any, str]:
        return self.entity, self.field, other, '<='

    def __eq__(self, other: Any) -> Tuple[Type[Entity], str, Any, str]:  # type: ignore
        return self.entity, self.field, other, '='

    def __ne__(self, other: Any) -> Tuple[Type[Entity], str, Any, str]:  # type: ignore
        return self.entity, self.field, other, '!='

    def __gt__(self, other: Any) -> Tuple[Type[Entity], str, Any, str]:
        return self.entity, self.field, other, '>'

    def __ge__(self, other: Any) -> Tuple[Type[Entity], str, Any, str]:
        return self.entity, self.field, other, '>='


def entity(entity_type: Type[T]) -> Type[T]:
    # Patch init to set id and queue for _new_entities as needed
    old_init = entity_type.__init__

    def new_init(self: T, *args: Any, **kwargs: Any) -> None:
        if 'id' in kwargs:  # Loaded from database
            obj_id = kwargs['id']
            del kwargs['id']
        else:  # Actually created a new entity
            # Take next id
            entity_type._next_id += 1
            obj_id = entity_type._next_id
            _new_entities.put_nowait(self)

        # Call old init to actually set the fields
        # ... except we can't do that on self (or any instance of its class)
        # TODO figure out why, according to Python manual it should work
        temp_obj = _FieldNames()
        # Raises on missing or extra values
        old_init(temp_obj, *args, **kwargs)  # type: ignore
        self.__dict__.update(temp_obj.__dict__)
        self.__dict__['id'] = obj_id  # Patch in id too
        self.__dict__['_destroyed'] = False

        # Cache this entity to its type (weakly referenced)
        entity_type._entity_cache[self.id] = self

        # Our __post_init__ replacement
        if hasattr(self, '__object_created__'):
            self.__object_created__()
    setattr(entity_type, '__init__', new_init)

    # Create cache (mainly to avoid duplicated entities in memory)
    entity_type._entity_cache = WeakValueDictionary()

    # Queue for async init
    _async_init_needed.add(entity_type)

    return entity_type


# Classes decorated with entity need some data injected from async DB callbacks
_async_init_needed: Set[Type[Entity]] = set()


async def _async_init_entities(conn: Connection, db_data: Path, prod_mode: bool) -> None:
    """Performs late/async initialization on entities."""
    logger.info("Initializing entity types...")
    migrator = TableMigrator(conn, db_data, prod_mode)
    await migrator.create_sys_tables()

    # Execute async/late init
    # Some tasks need accurate type information, and cannot be performed
    # earlier due to circular dependencies
    # Others are async, and cannot be waited on in the decorator
    for entity_type in _async_init_needed:
        # Figure out fields and create table schema based on them
        fields: Dict[str, Type[Any]] = {}
        for component in entity_type.mro():
            if component == object:
                continue  # Doesn't have anything interesting for us
            for name, field_type in component.__annotations__.items():
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
        field_names: _FieldNames = _FieldNames()
        for name in fields.keys():
            setattr(field_names, name, (OverloadedField(entity_type, name)))
        entity_type._field_names = field_names

        # Patch in change detection for fields
        def mark_changed(self: T, key: str, value: str) -> None:
            if not key.startswith('_'):  # Ignore non-DB fields
                # Queue to be saved and prevent GC before that happens
                _changed_entities.put_nowait(self)
            Entity.__setattr__(self, key, value)  # Update changed value to object
        setattr(entity_type, '__setattr__', mark_changed)
        # Queue table to be created/migrated
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

    logger.info(f"Found {len(_async_init_needed)} entity types")

    # Figure out and assign next free ids
    for entity_type in _async_init_needed:
        table_schema = entity_type._schema
        current_id = await conn.fetchval(f'SELECT max(id) FROM {table_schema["name"]}')
        entity_type._next_id = current_id + 1 if current_id else 0


# Newly created and changed entities that need to be saved to DB
_new_entities: asyncio.Queue[Entity] = asyncio.Queue()
_changed_entities: asyncio.Queue[Entity] = asyncio.Queue()


async def _save_entities() -> None:
    """Saves entities to DB as soon as they change."""
    # UPDATE changed entities
    async with _conn_pool.acquire() as conn:
        while True:
            entity = await _changed_entities.get()  # Block until entity is available
            if entity._destroyed:
                continue  # Skip entities that shouldn't be saved
            entity_type = type(entity)
            values = _obj_to_values(entity, entity_type._schema)
            try:
                status = await conn.execute(entity_type._sql_update, *values)
                if status == 'UPDATE 0':
                    raise AssertionError("UPDATE did not save entity")
            except Exception:
                logger.error(f"Saving changes of entity {entity} failed")
                logger.error(f"values: {values}")
                logger.error(f"sql: {entity_type._sql_update}")
                raise


async def _create_entities() -> None:
    """Creates entities in DB as soon as they've been init'd."""
    # INSERT newly created entities
    async with _conn_pool.acquire() as conn:
        while True:
            entity = await _new_entities.get()  # Block until entity is available
            await entity.__entity_created__()  # Call on created hook here (it is async)
            entity_type = type(entity)
            await conn.execute(entity_type._sql_insert, *_obj_to_values(entity, entity_type._schema))


async def init_entity_system(conn_pool: Pool, db_data: Path, prod_mode: bool, save_interval: float) -> None:
    # Reserve connection for 'one-shot' operations
    global _conn_pool
    _conn_pool = conn_pool

    # Perform async initialization as needed for entities
    async with conn_pool.acquire() as conn:
        async with conn.transaction():  # Either all migrations work, or none do
            await _async_init_entities(conn, db_data, prod_mode)
    _async_init_needed.clear()

    # Periodically save newly created and modified entities
    asyncio.create_task(_save_entities())
    asyncio.create_task(_create_entities())
