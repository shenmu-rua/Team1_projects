"""仅使用临时空表检查表头行为；不构造或读取业务记录。"""

import sqlite3

import pytest

from genshin_insight.schema import inspect_schema, render_dictionary


def test_inspect_declared_columns_and_keys(tmp_path):
    database = tmp_path / "empty.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE ods_record (record_key TEXT NOT NULL, pool_key TEXT NOT NULL, "
            "sequence INTEGER, PRIMARY KEY (record_key, pool_key))"
        )
        connection.execute("CREATE VIEW hidden_view AS SELECT record_key FROM ods_record")
    tables = inspect_schema(database)
    assert [table.name for table in tables] == ["ods_record"]
    columns = tables[0].columns
    assert [column.name for column in columns] == ["record_key", "pool_key", "sequence"]
    assert [column.declared_type for column in columns] == ["TEXT", "TEXT", "INTEGER"]
    assert [column.not_null for column in columns] == [True, True, False]
    assert [column.primary_key_position for column in columns] == [1, 2, 0]


def test_quoted_identifiers_and_generated_columns(tmp_path):
    database = tmp_path / "quoted.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            'CREATE TABLE "odd""name" ("field|name" INTEGER, '
            'derived INTEGER GENERATED ALWAYS AS ("field|name" + 1) VIRTUAL)'
        )
    tables = inspect_schema(database)
    assert tables[0].name == 'odd"name'
    assert tables[0].columns[1].hidden == 2
    dictionary = render_dictionary(tables)
    assert "field&#124;name" in dictionary
    assert "GENERATED ALWAYS" not in dictionary


def test_missing_database_is_not_created(tmp_path):
    database = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        inspect_schema(database)
    assert not database.exists()


def test_internal_tables_are_excluded(tmp_path):
    database = tmp_path / "internal.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE empty_table (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    assert [table.name for table in inspect_schema(database)] == ["empty_table"]
