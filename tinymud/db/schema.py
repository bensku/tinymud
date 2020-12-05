"""Table schema management tools."""

from enum import IntFlag
from dataclasses import dataclass, field
from typing import get_origin, get_args
from typing import Dict, ForwardRef, Generic, List, Optional, Tuple, TypedDict, TypeVar, Union


class Column(TypedDict):
    """A database table column."""
    name: str
    db_type: 'DbType'


def create_column(name: str, py_type: object) -> Column:
    """Creates a database column from Python type."""
    db_type = _to_db_type(py_type)
    return {'name': name, 'db_type': db_type}


T = TypeVar('T')


class _ForeignMarker(Generic[T]):
    """Marker for Foreign union in entity.py."""
    pass


Foreign = Union[int, _ForeignMarker[T]]


class DbType(TypedDict):
    """Database type."""
    name: str
    nullable: bool
    foreign_key: Optional[str]


def _new_db_type(name: str, nullable: bool = False, foreign_key: Optional[str] = None) -> DbType:
    return {'name': name, 'nullable': nullable, 'foreign_key': foreign_key}


def _to_db_type(py_type: object) -> DbType:
    """Maps a Python type to database type name."""
    if get_origin(py_type) == Union:  # Optional or foreign key
        args = get_args(py_type)  # Contains classes, not instances of them
        nullable = type(None) in args
        nonnull_count = len(args)
        if nullable:
            nonnull_count -= 1

        if nullable and len(args) == 2:
            # Optional[type] aliases to Union[type, None]
            db_type = _to_db_type(args[0])
            db_type['nullable'] = True  # Make type nullable
            return db_type
        elif nonnull_count == 2 and args[1].__origin__ == _ForeignMarker:
            # Foreign[entity_type] aliases to Union[int, _ForeignMarker[Entity]]
            # Nullable[Foreign[entity_type]] also aliases to very similar
            # Union[int, _ForeignMarker[Entity], None]
            # int is needed to support assigning ids to the type
            # _ForeignMarker contains referenced type (and marks for us)
            ref_table = new_table_name(get_args(args[1])[0])
            return _new_db_type('integer', nullable, ref_table)
        else:
            raise TypeError(f"unsupported union type {py_type}")
    elif py_type == bool:
        return _new_db_type('boolean')
    elif py_type == int:
        return _new_db_type('integer')
    elif py_type == float:
        return _new_db_type('double precision')
    elif py_type == str:
        return _new_db_type('text')
    elif isinstance(py_type, type) and issubclass(py_type, IntFlag):
        return _new_db_type('integer')
    else:
        raise TypeError(f"unsupported type {py_type}")


class TableSchema(TypedDict):
    """A database table schema."""
    name: str
    columns: List[Column]


def new_table_name(py_type: type) -> str:
    if isinstance(py_type, ForwardRef):
        return 'tinymud_' + py_type.__forward_arg__.lower()
    return 'tinymud_' + py_type.__name__.lower()


def new_table_schema(table_name: str, fields: Dict[str, type]) -> TableSchema:
    """Creates a new table schema from class fields."""
    columns: List[Column] = []

    # Rest of columns in alphabetical order
    for name in sorted(fields.keys()):
        if not name == 'id' and not name.startswith('_'):  # Ignore 'internal' fields
            columns.append(create_column(name, fields[name]))
    return {'name': table_name, 'columns': columns}


def get_create_table(table: TableSchema) -> str:
    """Gets CREATE TABLE statement for given table."""
    # Column creation rules (id is special)
    col_rows = ['id integer PRIMARY KEY']
    for column in table['columns']:
        db_type = column['db_type']
        row = f'{column["name"]} {db_type["name"]}'
        if not db_type['nullable']:
            row += ' NOT NULL'
        col_rows.append(row)

    cols_str = ',\n'.join(col_rows)
    return f'CREATE TABLE {table["name"]} (\n{cols_str}\n)'


def get_post_create(table: TableSchema) -> List[str]:
    """Gets statements to execute after all tables have been created.

    Foreign keys introduce (potentially circular) dependencies to empty tables,
    which makes creating them difficult. It is much easier to just ALTER TABLE
    the constraints in place afterwards.
    """
    sql = []
    name = table['name']
    for column in table['columns']:
        db_type = column['db_type']
        if 'foreign_key' in db_type and db_type['foreign_key']:
            colname = column["name"]
            sql.append(f'ALTER TABLE {name} DROP CONSTRAINT IF EXISTS fk_{colname}')
            sql.append((f'ALTER TABLE {name} ADD CONSTRAINT fk_{colname}'
                f' FOREIGN KEY ({colname})'
                f' REFERENCES {db_type["foreign_key"]}(id) ON DELETE CASCADE'))
    return sql


@dataclass
class AlterRequest:
    """A request to alter table."""
    description: str
    sql: List[str]
    input_needed: Dict[str, str] = field(default_factory=dict)


def update_table_schema(old_schema: TableSchema, fields: Dict[str, type]) -> Tuple[TableSchema, List[AlterRequest]]:
    """Creates an updated table schema based on current class fields.

    Columns in old schema that do not have matching fields are removed.
    New fields are given columns after other columns in alphabetical order.

    A new schema and a list of table alterations needed to implement it in an
    existing database are returned.
    """
    table_name = old_schema['name']
    old_columns = old_schema['columns']  # Won't modify this
    new_columns = old_columns.copy()  # Will remove and add columns here
    alter_requests: List[AlterRequest] = []  # Alter requests to show to users

    # Remove columns that no longer have fields
    field_names = fields.keys()
    old_names = []
    for column in old_columns:
        name = column['name']
        if name not in field_names:
            new_columns.remove(column)
            alter_requests.append(AlterRequest(f"drop column {name}",
                [f'ALTER TABLE {table_name} DROP COLUMN {name}']))
        else:
            old_names.append(name)

    # Append columns for new fields at end
    for name in sorted(fields.keys()):
        if name not in old_names:
            column = create_column(name, fields[name])
            new_columns.append(column)

            # SQL to add a new column for non-null columns is not one-liner
            db_type = column['db_type']
            sql = [f'ALTER TABLE {table_name} ADD COLUMN {name} {db_type["name"]}']
            if db_type['nullable']:
                alter_requests.append(AlterRequest(f"add nullable column {name}", sql))
            else:
                # These queries are written to SQL scripts, thus we can't use prepared statements
                # (not that there is any need, only trusted admins can use them)
                sql.append(f'UPDATE {table_name} SET {name} = $existing_value$')
                sql.append(f'ALTER TABLE {table_name} ALTER COLUMN {name} SET NOT NULL')
                alter_requests.append(AlterRequest(f"add non-null column {name}",
                    sql, {'$existing_value$': "value needed for existing rows"}))

    return {'name': table_name, 'columns': new_columns}, alter_requests


def get_sql_insert(table: TableSchema) -> str:
    """Creates SQL INSERT statement.

    $1: entity id, $2-$n: values of columns
    """
    columns = ['$1']  # id doesn't appear in columns
    for i, column in enumerate(table['columns']):
        columns.append(f'${i + 2}')
    return f'INSERT INTO {table["name"]} VALUES ({", ".join(columns)})'


def get_sql_select(table: str) -> str:
    """Creates SQL SELECT query without conditions."""
    return f'SELECT * FROM {table}'


def get_sql_update(table: TableSchema) -> str:
    """Creates SQL UPDATE statement.

    $1: entity id, $2-$n: values of columns
    """
    columns = []
    for i, column in enumerate(table['columns']):
        if column['name'] != 'id':  # Ignore id column, it is condition for update
            columns.append(f'{column["name"]} = ${i + 2}')
    return f'UPDATE {table["name"]} SET {", ".join(columns)} WHERE id = $1'


def get_sql_delete(table: str) -> str:
    """Creates SQL DELETE statement.

    $1: entity id
    """
    return f'DELETE FROM {table} WHERE id = $1'
