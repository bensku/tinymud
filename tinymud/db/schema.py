"""Table schema management tools."""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, TypedDict


class Column(TypedDict):
    """A database table column."""
    name: str
    db_type: str
    nullable: bool


def create_column(name: str, py_type: type) -> Column:
    """Creates a database column from Python type."""
    db_type, nullable = _to_db_type(py_type)
    return {'name': name, 'db_type': db_type, 'nullable': nullable}


def _to_db_type(py_type: type) -> Tuple[str, bool]:
    """Maps a Python type to database type name."""
    if hasattr(py_type, '__args__'):
        # Optional[type] aliases to Union[type, None]
        # Mypy has incomplete types here
        args: List[type] = py_type.__args__  # type: ignore
        # args contains classes, not instances of them
        if len(args) == 2 and args[1] == type(None):  # noqa: E721
            return _to_db_type(args[0])[0], True  # Nullable type
        else:
            raise TypeError(f"unsupported union type {py_type}")
    elif py_type == bool:
        return 'boolean', False
    elif py_type == int:
        return 'integer', False
    elif py_type == float:
        return 'double precision', False
    elif py_type == str:
        return 'text', False
    else:
        raise TypeError(f"unsupported type {py_type}")


class TableSchema(TypedDict):
    """A database table schema."""
    name: str
    columns: List[Column]


def new_table_schema(table_name: str, fields: Dict[str, type]) -> TableSchema:
    """Creates a new table schema from class fields."""
    columns: List[Column] = []
    # Id (primary key) always first
    columns.append(create_column('id', fields['id']))

    # Rest of columns in alphabetical order
    for name in sorted(fields.keys()):
        if not name == 'id' and not name.startswith('_'):  # Ignore 'internal' fields
            columns.append(create_column(name, fields[name]))
    return {'name': table_name, 'columns': columns}


def get_create_table(table: TableSchema) -> str:
    """Gets CREATE TABLE statement for given table."""
    # Column creation rules
    col_rows = []
    for column in table['columns']:
        row = f'{column["name"]} {column["db_type"]}'
        if not column['nullable']:
            row += ' NOT NULL'
        col_rows.append(row)

    cols_str = ',\n'.join(col_rows)
    return f'CREATE TABLE {table["name"]} (\n{cols_str}\n)'


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
            sql = [f'ALTER TABLE {table_name} ADD COLUMN {name} {column["db_type"]}']
            if column['nullable']:
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
    columns = []
    for i, column in enumerate(table['columns']):
        columns.append(f'${i}')
    return f'INSERT INTO {table} VALUES ({", ".join(columns)})'


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
            columns.append(f'{column["name"]} = ${i + 1}')
    return f'UPDATE {table} SET {", ".join(columns)} WHERE id = $1'


def get_sql_delete(table: str) -> str:
    """Creates SQL DELETE statement.

    $1: entity id
    """
    return f'DELETE FROM {table} WHERE id = $1'
