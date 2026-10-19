"""清洗契约的微型合成库；标识及内容均为测试虚构。"""

import sqlite3
from contextlib import closing

import pytest

SYNTHETIC_SCHEMA = """
CREATE TABLE datasets (dataset_id INTEGER PRIMARY KEY, code TEXT);
CREATE TABLE players (
    player_id INTEGER PRIMARY KEY, dataset_id INTEGER, player_key TEXT, uid_suffix TEXT);
CREATE TABLE gacha_types (
    gacha_type INTEGER PRIMARY KEY, pool_group INTEGER, pool_name TEXT, pool_group_name TEXT);
CREATE TABLE source_files (
    source_file_id INTEGER PRIMARY KEY, dataset_id INTEGER, player_id INTEGER,
    source_kind TEXT, relative_path TEXT);
CREATE TABLE items (item_id INTEGER PRIMARY KEY, name TEXT, item_type INTEGER, rank_type INTEGER);
CREATE TABLE pulls (
    pull_id INTEGER PRIMARY KEY, player_id INTEGER, source_file_id INTEGER, source_row INTEGER,
    item_id INTEGER, gacha_type INTEGER, pool_group INTEGER, pool_seq INTEGER,
    gacha_id TEXT, gacha_time TEXT);
CREATE TABLE rejected_rows (reject_id INTEGER PRIMARY KEY, raw_fields_json TEXT);
CREATE TABLE metadata (key TEXT, value_json TEXT);
CREATE TABLE resource_assets (content BLOB);
CREATE TABLE legacy_histograms (frequency INTEGER);
CREATE TABLE summary_pool (pulls INTEGER);
"""


@pytest.fixture
def source_factory(tmp_path):
    def create(rows=()):
        source = tmp_path / "synthetic_source.db"
        with closing(sqlite3.connect(source)) as connection:
            connection.executescript(SYNTHETIC_SCHEMA)
            connection.executemany(
                "INSERT INTO datasets VALUES (?, ?)", [(2, "test02"), (3, "test03")]
            )
            connection.executemany(
                "INSERT INTO players VALUES (?, ?, ?, ?)",
                [
                    (1, 2, "SYNTHETIC_PRIVATE_MARKER", "fake"),
                    (2, 3, "SYNTHETIC_PRIVATE_MARKER", "fake"),
                    (3, 3, "SYNTHETIC_PRIVATE_MARKER", "fake"),
                ],
            )
            connection.executemany(
                "INSERT INTO gacha_types VALUES (?, ?, ?, ?)",
                [
                    (301, 301, "test_a", "test_group"),
                    (400, 301, "test_b", "test_group"),
                ],
            )
            connection.executemany(
                "INSERT INTO source_files VALUES (?, ?, ?, ?, ?)",
                [
                    (11, 2, 1, "pull_csv", "SYNTHETIC_PRIVATE_MARKER"),
                    (22, 3, 2, "pull_csv", "SYNTHETIC_PRIVATE_MARKER"),
                    (33, 3, 3, "pull_csv", "SYNTHETIC_PRIVATE_MARKER"),
                ],
            )
            connection.executemany(
                "INSERT INTO items VALUES (?, ?, ?, ?)",
                [
                    (1, " Synthetic blade ", 1, 3),
                    (2, "Synthetic person", 0, 5),
                    (3, "Synthetic four", 1, 4),
                    (4, "Synthetic uncertain type", 0, 3),
                ],
            )
            connection.executemany("INSERT INTO pulls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            connection.executemany(
                "INSERT INTO rejected_rows VALUES (?, ?)",
                [
                    (1, "SYNTHETIC_PRIVATE_MARKER"),
                    (2, "SYNTHETIC_PRIVATE_MARKER"),
                ],
            )
            connection.commit()
        return source

    return create
