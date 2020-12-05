from enum import IntFlag, auto
import textwrap
from typing import Optional, get_type_hints

import tinymud.db.schema as schema


class MyFlag(IntFlag):
    ALPHA = auto()
    BETA = auto()
    GAMMA = auto()
    ALL = ALPHA | BETA | GAMMA


def test_column() -> None:
    required = schema.create_column('required', int)
    assert required['name'] == 'required'
    assert required['db_type'] == {'name': 'integer', 'nullable': False, 'foreign_key': None}

    optional = schema.create_column('optional', Optional[int])
    assert optional['db_type'] == {'name': 'integer', 'nullable': True, 'foreign_key': None}

    flag = schema.create_column('flag', MyFlag)
    assert flag['db_type'] == {'name': 'integer', 'nullable': False, 'foreign_key': None}


class DummyType:
    pass


class SampleClass:
    id: int
    name: str
    weight: Optional[float]
    flag: bool
    table_ref: schema.Foreign[DummyType]


# Specifying Foreign[type] in dict does not pass type check
# Real-world use-case works, but still... TODO investigate
sample_fields = {}
for name, field_type in get_type_hints(SampleClass).items():
    sample_fields[name] = field_type


def test_table_schema() -> None:
    fields = sample_fields
    table = schema.new_table_schema('table', fields)
    assert table['name'] == 'table'

    for column in table['columns']:
        assert column['name'] in fields
        py_type = fields[column['name']]
        expected = schema.create_column('_', py_type)
        assert expected['db_type'] == column['db_type']


def test_create_table() -> None:
    stmt = schema.get_create_table(schema.new_table_schema('FooTable', sample_fields))
    expected = textwrap.dedent("""    CREATE TABLE FooTable (
    id integer PRIMARY KEY,
    flag boolean NOT NULL,
    name text NOT NULL,
    table_ref integer NOT NULL,
    weight double precision
    )""")
    assert stmt == expected


def test_post_create() -> None:
    stmt = schema.get_post_create(schema.new_table_schema('FooTable', sample_fields))
    assert stmt == [
        'ALTER TABLE FooTable DROP CONSTRAINT IF EXISTS fk_table_ref',
        ('ALTER TABLE FooTable ADD CONSTRAINT fk_table_ref FOREIGN KEY (table_ref) '
            'REFERENCES tinymud_dummytype(id) ON DELETE CASCADE')
    ]


def test_schema_update() -> None:
    old_fields = sample_fields
    new_fields = {
        'weight': Optional[float],
        'flag': bool,
        'new_field': str
    }
    old_schema = schema.new_table_schema('FooTable', old_fields)
    new_schema, alter_reqs = schema.update_table_schema(old_schema, new_fields)

    # Is the new schema correct?
    expected = textwrap.dedent("""    CREATE TABLE FooTable (
    id integer PRIMARY KEY,
    flag boolean NOT NULL,
    weight double precision,
    new_field text NOT NULL
    )""")
    assert schema.get_create_table(new_schema) == expected

    # Are ALTER requests able to change table to it?
    assert alter_reqs[0].sql == ['ALTER TABLE FooTable DROP COLUMN name']
    assert alter_reqs[1].sql == ['ALTER TABLE FooTable DROP COLUMN table_ref']
    assert alter_reqs[2].sql == [
        'ALTER TABLE FooTable ADD COLUMN new_field text',
        'UPDATE FooTable SET new_field = $existing_value$',
        'ALTER TABLE FooTable ALTER COLUMN new_field SET NOT NULL'
    ]
