"""合成端到端：去重保守性、隔离、可追溯、对账和输入保护。"""

import hashlib
import json
import sqlite3
from contextlib import closing

import pytest

from genshin_insight.db import cleaning_connection
from genshin_insight.pipeline import clean_database


def pull(
    key,
    *,
    player=2,
    source=22,
    row=None,
    item=1,
    pool=301,
    sequence=1,
    identity="900",
    timestamp="2022-01-01 00:00:00",
):
    return (
        key,
        player,
        source,
        row if row is not None else key + 1,
        item,
        pool,
        301 if pool == 400 else pool,
        sequence,
        identity,
        timestamp,
    )


def test_cleaning_row_accounting_and_conservative_rules(source_factory, tmp_path):
    rows = [
        pull(1, player=1, source=11, row=2, identity=None, sequence=99),
        pull(2, player=1, source=11, row=3, identity=None, sequence=2),
        pull(3, item=2),
        pull(4, item=2),
        pull(5, identity="901"),
        pull(6, identity="901", item=3),
        pull(7, identity="902", timestamp="2022-02-30 00:00:00"),
        pull(8, identity=None),
        pull(9, identity="bad-id"),
        pull(10, identity="910", item=999),
        pull(11, identity="911", pool=999),
        pull(12, identity="903", item=4, timestamp="2022-01-02 00:00:00"),
        pull(13, player=3, source=33, item=2),
        pull(
            14, player=1, source=11, row=4, identity=None, pool=400, timestamp="2022-01-03 00:00:00"
        ),
        pull(15, player=1, source=11, row=5, identity=None, timestamp="2022-01-04 00:00:00"),
        pull(16, player=1, source=11, row=6, identity=None, timestamp="2022-01-05 00:00:00"),
        pull(17, player=1, source=11, row=6, identity=None, timestamp="2022-01-05 00:00:00"),
        pull(18, player=1, source=11, row=7, identity=None),
        pull(19, player=1, source=11, row=7, identity=None, item=3),
        pull(20, player=2, source=11),
        pull(21, player=999),
        pull(22, row=1),
        pull(23, identity="904", timestamp=" 2022-01-03T00:00:00 "),
    ]
    source = source_factory(rows)
    before = hashlib.sha256(source.read_bytes()).digest()
    output = tmp_path / "cleaned.db"
    report = clean_database(source, output)
    assert hashlib.sha256(source.read_bytes()).digest() == before
    metrics = report["metrics"]
    assert metrics["input_pulls"] == 23
    assert metrics["kept_pulls"] == 9
    assert metrics["rejected_pulls"] == 14
    assert metrics["duplicate_rows_removed"] == 2
    assert metrics["conflicting_rows_quarantined"] == 4
    assert metrics["players_in_cleaned_pulls"] == 3
    assert metrics["item_type_review_pulls"] == 3
    assert metrics["item_type_review_sources"] == 1
    assert metrics["timestamp_normalized_pulls"] == 1
    assert metrics["ambiguous_same_second_pulls"] == 2
    assert metrics["preexisting_import_rejected_rows"] == 2
    assert all(check["passed"] for check in report["checks"])
    with closing(sqlite3.connect(output)) as connection:
        kept_keys = {row[0] for row in connection.execute("SELECT pull_id FROM dwd_pull")}
        assert kept_keys == {1, 2, 3, 12, 13, 14, 15, 16, 23}
        assert connection.execute("SELECT name FROM dim_item WHERE item_id=1").fetchone()[0] == (
            "Synthetic blade"
        )
        assert list(
            connection.execute("""SELECT pool_seq FROM dwd_pull WHERE player_id=1
            ORDER BY pool_seq""")
        ) == [(1,), (2,), (3,), (4,), (5,)]
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        forbidden = {
            "uid",
            "uid_suffix",
            "player_key",
            "gacha_id",
            "relative_path",
            "raw_fields_json",
            "content",
        }
        for table in tables:
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            assert not columns.intersection(forbidden)
        assert connection.execute(
            "SELECT count(*) FROM dq_check_result WHERE NOT passed"
        ).fetchone() == (0,)
    contents = output.with_suffix(".json").read_text(encoding="utf-8")
    assert "SYNTHETIC_PRIVATE_MARKER" not in contents
    assert json.loads(contents)["status"] == "success"


def test_numeric_id_ordering_preserves_arbitrary_precision(source_factory, tmp_path):
    source = source_factory(
        [
            pull(1, identity="100000000000000000000"),
            pull(2, identity="99999999999999999999"),
        ]
    )
    output = tmp_path / "numeric.db"
    clean_database(source, output)
    with closing(sqlite3.connect(output)) as connection:
        assert list(connection.execute("SELECT pull_id FROM dwd_pull ORDER BY pool_seq")) == [
            (2,),
            (1,),
        ]


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT player_key FROM source.players",
        "SELECT uid_suffix FROM source.players",
        "SELECT relative_path FROM source.source_files",
        "SELECT raw_fields_json FROM source.rejected_rows",
        "SELECT * FROM source.metadata",
        "SELECT * FROM source.resource_assets",
        "SELECT * FROM source.legacy_histograms",
        "SELECT * FROM source.summary_pool",
        "UPDATE source.pulls SET pool_seq=1",
        "DROP TABLE source.pulls",
        "ATTACH DATABASE ':memory:' AS another",
    ],
)
def test_source_guard_denies_unneeded_content_and_writes(source_factory, tmp_path, statement):
    source = source_factory()
    temporary = tmp_path / "guard.db"
    temporary.touch()
    with cleaning_connection(source, temporary) as connection:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute(statement)


def test_existing_output_is_preserved(source_factory, tmp_path):
    source = source_factory()
    output = tmp_path / "existing.db"
    output.write_bytes(b"synthetic-existing-output")
    with pytest.raises(FileExistsError):
        clean_database(source, output)
    assert output.read_bytes() == b"synthetic-existing-output"
    with pytest.raises(ValueError):
        clean_database(source, source)


def test_failure_does_not_publish_partial_database(source_factory, tmp_path):
    source = source_factory()
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("DROP TABLE items")
        connection.commit()
    output = tmp_path / "failed.db"
    with pytest.raises(RuntimeError, match="源库未改写"):
        clean_database(source, output)
    assert not output.exists()
    assert not list(tmp_path.glob("*.partial"))


def test_empty_source_produces_consistent_empty_result(source_factory, tmp_path):
    source = source_factory()
    report = clean_database(source, tmp_path / "empty.db")
    assert report["metrics"]["input_pulls"] == report["metrics"]["kept_pulls"] == 0
    assert all(check["passed"] for check in report["checks"])
