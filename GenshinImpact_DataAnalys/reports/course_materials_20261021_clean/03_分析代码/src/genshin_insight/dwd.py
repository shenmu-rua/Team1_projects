"""明细清洗：明确拒绝原因，保留无 ID 重复外观记录，重建池内序号。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from . import config


def normalize_time(value: object) -> str | None:
    """只接收秒级无时区时间；校验日历，不猜测或转换时区。"""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) != 19 or text[10] not in {" ", "T"}:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    result = parsed.isoformat(sep=" ", timespec="seconds")
    return result if text.replace("T", " ") == result else None


def stage_pulls(connection: sqlite3.Connection) -> None:
    connection.create_function("normalize_time", 1, normalize_time, deterministic=True)
    connection.execute("""CREATE TEMP TABLE stage_pull (
        pull_id INTEGER PRIMARY KEY, player_id INTEGER, dataset_id INTEGER,
        source_file_id INTEGER, source_row INTEGER, item_id INTEGER,
        gacha_type INTEGER, pool_group INTEGER, source_pool_seq INTEGER,
        gacha_id TEXT, source_time TEXT, gacha_time TEXT,
        source_player_id INTEGER, source_dataset_id INTEGER, source_pool_group INTEGER,
        valid_item INTEGER, valid_gacha_type INTEGER, invalid_id_storage INTEGER,
        rejection_reason TEXT)""")
    connection.execute("""INSERT INTO stage_pull
        SELECT r.pull_id, p.player_id, p.dataset_id, r.source_file_id, r.source_row,
               r.item_id, r.gacha_type, g.pool_group,
               CASE WHEN typeof(r.pool_seq) = 'integer' THEN r.pool_seq END,
               CASE WHEN typeof(r.gacha_id) = 'text'
                    THEN NULLIF(trim(r.gacha_id, char(9,10,11,12,13,32)), '') END,
               CASE WHEN typeof(r.gacha_time) = 'text' THEN r.gacha_time END,
               normalize_time(CASE WHEN typeof(r.gacha_time) = 'text' THEN r.gacha_time END),
               s.player_id, s.dataset_id, r.pool_group, i.item_id, g.gacha_type,
               typeof(r.gacha_id) NOT IN ('text', 'null'), NULL
        FROM source.pulls r
        LEFT JOIN dim_player p ON p.player_id = r.player_id
        LEFT JOIN dim_source s ON s.source_file_id = r.source_file_id
        LEFT JOIN dim_item i ON i.item_id = r.item_id
        LEFT JOIN dim_gacha_type g ON g.gacha_type = r.gacha_type""")
    required_ids = ",".join(str(value) for value in config.ID_REQUIRED_DATASET_IDS) or "NULL"
    connection.execute(f"""UPDATE stage_pull SET rejection_reason = CASE
        WHEN player_id IS NULL THEN 'invalid_player_reference'
        WHEN source_player_id IS NULL OR source_player_id != player_id
          OR source_dataset_id != dataset_id THEN 'invalid_source_reference'
        WHEN typeof(source_row) != 'integer' OR source_row < 2 THEN 'invalid_source_row'
        WHEN valid_item IS NULL THEN 'invalid_item_reference'
        WHEN valid_gacha_type IS NULL THEN 'invalid_gacha_type'
        WHEN source_pool_group IS NULL OR source_pool_group != pool_group THEN 'pool_group_mismatch'
        WHEN gacha_time IS NULL THEN 'invalid_timestamp'
        WHEN invalid_id_storage OR (gacha_id IS NOT NULL AND gacha_id GLOB '*[^0-9]*')
          THEN 'invalid_gacha_id'
        WHEN dataset_id IN ({required_ids}) AND gacha_id IS NULL THEN 'missing_gacha_id'
        ELSE NULL END""")


def deduplicate(connection: sqlite3.Connection) -> None:
    # 先按物理来源行处理，再按账号内业务 ID；每行只有一个最终去向。
    connection.execute("""CREATE INDEX temp.idx_stage_source
        ON stage_pull(source_file_id, source_row) WHERE rejection_reason IS NULL""")
    connection.execute("""CREATE TEMP TABLE duplicate_source AS
        SELECT source_file_id, source_row, min(pull_id) AS keeper,
               (min(player_id) != max(player_id) OR min(item_id) != max(item_id)
                OR min(gacha_type) != max(gacha_type) OR min(gacha_time) != max(gacha_time)
                OR min(coalesce(gacha_id, '')) != max(coalesce(gacha_id, ''))) AS conflict
        FROM stage_pull WHERE rejection_reason IS NULL
        GROUP BY source_file_id, source_row HAVING count(*) > 1""")
    connection.execute("""UPDATE stage_pull SET rejection_reason = 'conflicting_provenance'
        WHERE pull_id IN (
            SELECT s.pull_id FROM stage_pull s JOIN duplicate_source d
              ON d.source_file_id = s.source_file_id AND d.source_row = s.source_row
            WHERE s.rejection_reason IS NULL AND d.conflict)""")
    connection.execute("""UPDATE stage_pull SET rejection_reason = 'duplicate_provenance'
        WHERE pull_id IN (
            SELECT s.pull_id FROM stage_pull s JOIN duplicate_source d
              ON d.source_file_id = s.source_file_id AND d.source_row = s.source_row
            WHERE s.rejection_reason IS NULL AND NOT d.conflict AND s.pull_id != d.keeper)""")
    connection.execute("""CREATE INDEX temp.idx_stage_business_id
        ON stage_pull(player_id, gacha_id)
        WHERE rejection_reason IS NULL AND gacha_id IS NOT NULL""")
    connection.execute("""CREATE TEMP TABLE duplicate_business_id AS
        SELECT player_id, gacha_id, min(pull_id) AS keeper,
               (min(item_id) != max(item_id) OR min(gacha_type) != max(gacha_type)
                OR min(gacha_time) != max(gacha_time)) AS conflict
        FROM stage_pull WHERE rejection_reason IS NULL AND gacha_id IS NOT NULL
        GROUP BY player_id, gacha_id HAVING count(*) > 1""")
    connection.execute("""UPDATE stage_pull SET rejection_reason = 'conflicting_gacha_id'
        WHERE pull_id IN (
            SELECT s.pull_id FROM stage_pull s JOIN duplicate_business_id d
              ON d.player_id = s.player_id AND d.gacha_id = s.gacha_id
            WHERE s.rejection_reason IS NULL AND d.conflict)""")
    connection.execute("""UPDATE stage_pull SET rejection_reason = 'duplicate_gacha_id'
        WHERE pull_id IN (
            SELECT s.pull_id FROM stage_pull s JOIN duplicate_business_id d
              ON d.player_id = s.player_id AND d.gacha_id = s.gacha_id
            WHERE s.rejection_reason IS NULL AND NOT d.conflict AND s.pull_id != d.keeper)""")


def write_details(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TEMP TABLE review_source AS
        SELECT DISTINCT s.source_file_id FROM stage_pull s JOIN dim_item i ON i.item_id = s.item_id
        WHERE i.rank_type = 3 AND i.item_type = 0""")
    connection.execute(
        "CREATE UNIQUE INDEX temp.idx_review_source ON review_source(source_file_id)"
    )
    connection.execute("""CREATE TABLE dwd_pull (
        pull_id INTEGER PRIMARY KEY,
        dataset_id INTEGER NOT NULL REFERENCES dim_dataset(dataset_id),
        player_id INTEGER NOT NULL REFERENCES dim_player(player_id),
        source_file_id INTEGER NOT NULL REFERENCES dim_source(source_file_id),
        source_row INTEGER NOT NULL CHECK(source_row >= 2),
        item_id INTEGER NOT NULL REFERENCES dim_item(item_id),
        gacha_type INTEGER NOT NULL REFERENCES dim_gacha_type(gacha_type),
        pool_group INTEGER NOT NULL,
        pool_seq INTEGER NOT NULL CHECK(pool_seq >= 1), source_pool_seq INTEGER,
        gacha_time TEXT NOT NULL,
        item_type_review INTEGER NOT NULL CHECK(item_type_review IN (0,1)),
        time_order_ambiguous INTEGER NOT NULL CHECK(time_order_ambiguous IN (0,1)),
        time_normalized INTEGER NOT NULL CHECK(time_normalized IN (0,1)))""")
    connection.execute("""INSERT INTO dwd_pull
        SELECT s.pull_id, s.dataset_id, s.player_id, s.source_file_id, s.source_row,
               s.item_id, s.gacha_type, s.pool_group,
               row_number() OVER (
                   PARTITION BY s.player_id, s.pool_group
                   ORDER BY s.gacha_time,
                            CASE WHEN s.gacha_id IS NULL THEN 0 ELSE 1 END,
                            length(ltrim(s.gacha_id, '0')), ltrim(s.gacha_id, '0'),
                            s.source_file_id, s.source_row, s.pull_id),
               s.source_pool_seq, s.gacha_time, r.source_file_id IS NOT NULL,
               (count(*) OVER same_second > 1
                AND sum(s.gacha_id IS NULL) OVER same_second > 0),
               s.gacha_time != s.source_time
        FROM stage_pull s LEFT JOIN review_source r ON r.source_file_id = s.source_file_id
        WHERE s.rejection_reason IS NULL
        WINDOW same_second AS (PARTITION BY s.player_id, s.pool_group, s.gacha_time)""")
    connection.execute("""CREATE TABLE dwd_rejected_pull (
        pull_id INTEGER PRIMARY KEY, reason TEXT NOT NULL)""")
    connection.execute("""INSERT INTO dwd_rejected_pull
        SELECT pull_id, rejection_reason FROM stage_pull WHERE rejection_reason IS NOT NULL""")
    connection.execute("""CREATE UNIQUE INDEX idx_dwd_player_pool_seq
        ON dwd_pull(player_id, pool_group, pool_seq)""")
    connection.execute("""CREATE INDEX idx_dwd_time_pool
        ON dwd_pull(gacha_time, pool_group)""")
