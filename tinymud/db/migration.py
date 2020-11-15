"""High-level data migration utils."""

import json
from typing import List, Optional
from pathlib import Path

from asyncpg import Connection
from asyncpg.exceptions import PostgresError

from .schema import TableSchema, get_create_table, get_post_create


class MigrationException(Exception):
    pass


class TableMigrator:
    def __init__(self, conn: Connection, db_data: Path, prod_mode: bool):
        self.conn = conn
        self.migrations = db_data / 'migrations'
        self.schemas = db_data / 'schemas'
        self.prod_mode = prod_mode
        self._new_table_queue: List[TableSchema] = []
        self._migration_queue: List[TableSchema] = []

    async def _get_migration_level(self, table: str) -> Optional[int]:
        """Gets current migration level of a table.

        Returns current migration level (integer) for existing tables and None
        for those that have not yet been created."""
        return await self.conn.fetchval('SELECT level FROM tinymud_migrations WHERE table_name = $1', table)

    async def _set_migration_level(self, table: str, level: int) -> None:
        """Sets current migration level of a table."""
        await self.conn.execute('UPDATE tinymud_migrations SET level = $1 WHERE table_name = $2', level, table)

    async def _schema_valid_prod(self, table: TableSchema) -> bool:
        """Checks if schema of given table is valid for production.

        When the schemas stored in db_data/schemas and generated from current
        Python classes differ, some tables probably need migrations that have
        not been written yet. A developer must address this before pushing to
        production (or production-like database).
        """
        try:
            with open(self.schemas / table['name'] + '.json', 'r') as f:
                disk_schema = json.load(f)
                return table == disk_schema  # Compare schema content
        except FileNotFoundError:
            return False  # No schema found!

    async def _run_script(self, path: Path) -> None:
        """Loads an SQL script from file and run it."""
        with open(path, 'r') as f:
            self.conn.executemany(f.read())

    def _needs_migrations(self, table: str, current_level: int) -> bool:
        """Checks if a table needs migrations."""
        sql_dir = self.migrations / table
        if not sql_dir.exists():
            if current_level > 0:  # Where did the previous migrations go?
                raise MigrationException(f"{table} already has {current_level}, but directory is missing")
            else:  # No migrations? That's ok
                return False

        # TODO return paths to migrations that need to be applied
        # (would avoid listing files)
        for migration in sorted(sql_dir.iterdir()):
            level = int(migration.name.split('_')[0])
            if level > current_level:  # Not yet applied
                return True  # Need to apply it later
        return False  # Up to date!

    async def _run_migrations(self, table: str, current_level: int) -> int:
        """Run migrations that have not been applied yet."""
        sql_dir = self.migrations / table
        if not sql_dir.exists():
            if current_level > 0:  # Where did the previous migrations go?
                raise MigrationException(f"{table} already has {current_level}, but directory is missing")
            else:  # No migrations? That's ok
                return 0
        for migration in sorted(sql_dir.iterdir()):
            level = int(migration.name.split('_')[0])
            if level > current_level:  # Not yet applied
                await self._run_script(sql_dir / migration)

        if level != current_level:  # Update migration level if needed
            await self._set_migration_level(table, level)
        return level

    async def _create_table(self, table: TableSchema) -> None:
        """Creates a new table."""
        try:
            await self.conn.execute(get_create_table(table))
        except PostgresError:  # Only DB related exceptions
            print(f"Failed to execute CREATE TABLE for {table['name']}")
            raise
        # Initialize migration level (so that it can be altered in future)
        await self.conn.execute('INSERT INTO tinymud_migrations (table_name, level) VALUES ($1, $2)', table['name'], 0)

    async def create_sys_tables(self) -> None:
        """Creates system tables in database.

        Call this before attempting to migrate anything. This is safe even if
        the tables already exist.
        """
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS tinymud_migrations (
            table_name TEXT,
            level INTEGER
        )""")

    async def add_table(self, table: TableSchema) -> None:
        """Queues given table to be created or migrated.

        While this does not create the table, database is queried for its
        existency. Returns amount of tables that needed to be created.
        """
        name = table['name']
        # Do a basic sanity check if we're in production environment
        if self.prod_mode and not await self._schema_valid_prod(table):
            raise MigrationException(f"in prod, and table {name} has outdated schema")

        current_level = await self._get_migration_level(name)
        if current_level is None:  # New table
            self._new_table_queue.append(table)
        elif self._needs_migrations(name, current_level):  # Needs migration
            self._migration_queue.append(table)
        # else: no need to do anything for this table

    # TODO WIP, finish this before moving on!

    async def create_tables(self) -> int:
        """Creates tables that do not exist yet."""
        for table in self._new_table_queue:
            await self._create_table(table)
        return len(self._new_table_queue)

    async def migrate_tables(self) -> int:
        """Migrates tables that already exist but need their columns changed.

        Returns number of tables that needed migration.
        """
        for table in self._migration_queue:
            current_level = await self._get_migration_level(table['name'])
            assert current_level is not None
            await self._run_migrations(table['name'], current_level)
        return len(self._migration_queue)

    async def exec_post_create(self) -> int:
        """Executes post create statements.

        Some tables that were created or migrated might need ALTER TABLE or two
        to add foreign keys etc.

        Returns amount of statements executed.
        """
        stmt_count = 0
        for table in self._new_table_queue:
            sql = get_post_create(table)
            for stmt in sql:
                await self.conn.execute(stmt)
            stmt_count += len(sql)
        return stmt_count
