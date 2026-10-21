"""生成清洗使用的维表，不复制个人标识、源路径或原始载荷。"""

from __future__ import annotations

import sqlite3


def normalize_name(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def build_dimensions(connection: sqlite3.Connection) -> None:
    connection.create_function("normalize_name", 1, normalize_name, deterministic=True)
    statements = [
        """CREATE TABLE dim_dataset (
            dataset_id INTEGER PRIMARY KEY, code TEXT NOT NULL)""",
        """INSERT INTO dim_dataset
            SELECT dataset_id, normalize_name(code) FROM source.datasets
            WHERE typeof(dataset_id) = 'integer' AND dataset_id > 0
              AND typeof(code) = 'text' AND normalize_name(code) IS NOT NULL""",
        """CREATE TABLE dim_player (
            player_id INTEGER PRIMARY KEY,
            dataset_id INTEGER NOT NULL REFERENCES dim_dataset(dataset_id))""",
        """INSERT INTO dim_player
            SELECT p.player_id, p.dataset_id FROM source.players p
            JOIN dim_dataset d ON d.dataset_id = p.dataset_id
            WHERE typeof(p.player_id) = 'integer' AND p.player_id > 0""",
        """CREATE TABLE dim_source (
            source_file_id INTEGER PRIMARY KEY,
            dataset_id INTEGER NOT NULL REFERENCES dim_dataset(dataset_id),
            player_id INTEGER NOT NULL REFERENCES dim_player(player_id))""",
        """INSERT INTO dim_source
            SELECT s.source_file_id, s.dataset_id, s.player_id FROM source.source_files s
            JOIN dim_player p ON p.player_id = s.player_id AND p.dataset_id = s.dataset_id
            WHERE s.source_kind = 'pull_csv' AND typeof(s.source_file_id) = 'integer'
              AND s.source_file_id > 0""",
        """CREATE TABLE dim_item (
            item_id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            item_type INTEGER NOT NULL CHECK(item_type IN (0, 1)),
            rank_type INTEGER NOT NULL CHECK(rank_type IN (3, 4, 5)))""",
        """INSERT INTO dim_item
            SELECT item_id, normalize_name(name), item_type, rank_type FROM source.items
            WHERE typeof(item_id) = 'integer' AND item_id > 0 AND typeof(name) = 'text'
              AND normalize_name(name) IS NOT NULL AND typeof(item_type) = 'integer'
              AND typeof(rank_type) = 'integer' AND item_type IN (0, 1) AND rank_type IN (3, 4, 5)""",
        """CREATE TABLE dim_gacha_type (
            gacha_type INTEGER PRIMARY KEY, pool_group INTEGER NOT NULL,
            pool_name TEXT NOT NULL, pool_group_name TEXT NOT NULL)""",
        """INSERT INTO dim_gacha_type
            SELECT gacha_type, pool_group, normalize_name(pool_name), normalize_name(pool_group_name)
            FROM source.gacha_types WHERE typeof(gacha_type) = 'integer' AND gacha_type > 0
              AND typeof(pool_group) = 'integer' AND pool_group > 0
              AND typeof(pool_name) = 'text' AND normalize_name(pool_name) IS NOT NULL
              AND typeof(pool_group_name) = 'text' AND normalize_name(pool_group_name) IS NOT NULL""",
    ]
    for statement in statements:
        connection.execute(statement)
