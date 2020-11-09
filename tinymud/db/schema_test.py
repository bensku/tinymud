import textwrap
from typing import Optional

import tinymud.db.schema as schema


def test_column():
    required = schema.create_column('required', int)
    assert required['name'] == 'required'
    assert required['db_type'] == 'integer'
    assert required['nullable'] is False

    optional = schema.create_column('optional', Optional[int])
    assert optional['db_type'] == 'integer'
    assert optional['nullable'] is True


sample_fields = {
    'id': int,
    'name': str,
    'weight': Optional[float],
    'flag': bool
}


def test_table_schema():
    fields = sample_fields
    table = schema.new_table_schema('table', fields)
    assert table['name'] == 'table'

    for column in table['columns']:
        assert column['name'] in fields
        py_type = fields[column['name']]
        expected = schema.create_column('_', py_type)
        assert expected['db_type'] == column['db_type']
        assert expected['nullable'] == column['nullable']


def test_create_table():
    stmt = schema.get_create_table(schema.new_table_schema('FooTable', sample_fields))
    expected = textwrap.dedent("""    CREATE TABLE FooTable (
    id integer NOT NULL,
    flag boolean NOT NULL,
    name text NOT NULL,
    weight double precision
    )""")
    assert stmt == expected


def test_schema_update():
    old_fields = sample_fields
    new_fields = {
        'id': int,
        'weight': Optional[float],
        'flag': bool,
        'new_field': str
    }
    old_schema = schema.new_table_schema('FooTable', old_fields)
    new_schema, alter_reqs = schema.update_table_schema(old_schema, new_fields)

    # Is the new schema correct?
    expected = textwrap.dedent("""    CREATE TABLE FooTable (
    id integer NOT NULL,
    flag boolean NOT NULL,
    weight double precision,
    new_field text NOT NULL
    )""")
    assert schema.get_create_table(new_schema) == expected

    # Are ALTER requests able to change table to it?
    assert alter_reqs[0].sql == ['ALTER TABLE FooTable DROP COLUMN name']
    assert alter_reqs[1].sql == [
        'ALTER TABLE FooTable ADD COLUMN new_field text',
        'UPDATE FooTable SET new_field = $existing_value$',
        'ALTER TABLE FooTable ALTER COLUMN new_field SET NOT NULL'
    ]
