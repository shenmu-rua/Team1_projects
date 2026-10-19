"""本地清洗连接；源库只读，源表和列使用允许清单。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SOURCE_COLUMNS = {
    "datasets": {"dataset_id", "code"},
    "players": {"player_id", "dataset_id"},
    "gacha_types": {"gacha_type", "pool_group", "pool_name", "pool_group_name"},
    "items": {"item_id", "name", "item_type", "rank_type"},
    "source_files": {"source_file_id", "dataset_id", "player_id", "source_kind"},
    "pulls": {
        "pull_id",
        "player_id",
        "source_file_id",
        "source_row",
        "item_id",
        "gacha_type",
        "pool_group",
        "pool_seq",
        "gacha_id",
        "gacha_time",
    },
    "rejected_rows": set(),  # 仅允许 COUNT(*)，不允许读取拒绝记录的任何列。
}


def _cleaning_authorizer(action, argument, detail, database, trigger):
    if action == sqlite3.SQLITE_READ and database == "source":
        if argument in {"sqlite_master", "sqlite_schema"}:
            return sqlite3.SQLITE_OK
        if argument in SOURCE_COLUMNS and (not detail or detail in SOURCE_COLUMNS[argument]):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    if database == "source" and action not in {
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_PRAGMA,
    }:
        return sqlite3.SQLITE_DENY
    if action in {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (detail or "").lower() in {
        "load_extension",
        "readfile",
        "writefile",
    }:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


@contextmanager
def cleaning_connection(
    source: str | Path, destination: str | Path
) -> Iterator[sqlite3.Connection]:
    """destination 必须是调用者独占创建的临时库；源库按 mode=ro 附加。"""
    source_path = Path(source).resolve(strict=True)
    destination_path = Path(destination).resolve(strict=True)
    if source_path == destination_path or source_path.samefile(destination_path):
        raise ValueError("清洗目标不得与源库相同。")
    connection = sqlite3.connect(f"{destination_path.as_uri()}?mode=rw", uri=True)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA cache_size = -65536")
        connection.execute("PRAGMA temp_store = FILE")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("ATTACH DATABASE ? AS source", (f"{source_path.as_uri()}?mode=ro",))
        connection.set_authorizer(_cleaning_authorizer)
        yield connection
    finally:
        connection.close()
