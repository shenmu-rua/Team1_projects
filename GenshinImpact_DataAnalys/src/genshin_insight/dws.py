"""从本次清洗后的明细重建汇总；不读取旧 summary 或 legacy 表。"""

import sqlite3


def build_summaries(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE dws_player_pool AS
        SELECT r.player_id, r.dataset_id, r.pool_group, count(*) AS pulls,
               sum(i.rank_type = 3) AS star3, sum(i.rank_type = 4) AS star4,
               sum(i.rank_type = 5) AS star5,
               min(r.gacha_time) AS first_time, max(r.gacha_time) AS last_time,
               sum(r.item_type_review) AS item_type_review_pulls,
               sum(r.time_order_ambiguous) AS ambiguous_order_pulls
        FROM dwd_pull r JOIN dim_item i ON i.item_id = r.item_id
        GROUP BY r.player_id, r.dataset_id, r.pool_group""")
    connection.execute("""CREATE UNIQUE INDEX idx_dws_player_pool
        ON dws_player_pool(player_id, pool_group)""")
    connection.execute("""CREATE TABLE dws_pool AS
        SELECT r.dataset_id, r.gacha_type, r.pool_group, count(*) AS pulls,
               count(DISTINCT r.player_id) AS players,
               sum(i.rank_type = 3) AS star3, sum(i.rank_type = 4) AS star4,
               sum(i.rank_type = 5) AS star5,
               sum(r.item_type_review) AS item_type_review_pulls,
               min(r.gacha_time) AS first_time, max(r.gacha_time) AS last_time
        FROM dwd_pull r JOIN dim_item i ON i.item_id = r.item_id
        GROUP BY r.dataset_id, r.gacha_type, r.pool_group""")
    connection.execute("""CREATE TABLE dws_daily AS
        SELECT r.dataset_id, substr(r.gacha_time, 1, 10) AS pull_date,
               r.gacha_type, r.pool_group, i.rank_type, count(*) AS pulls,
               count(DISTINCT r.player_id) AS players
        FROM dwd_pull r JOIN dim_item i ON i.item_id = r.item_id
        GROUP BY r.dataset_id, pull_date, r.gacha_type, r.pool_group, i.rank_type""")
    connection.execute("""CREATE TABLE dws_item AS
        SELECT r.dataset_id, r.gacha_type, r.item_id, count(*) AS pulls,
               count(DISTINCT r.player_id) AS players,
               sum(r.item_type_review) AS item_type_review_pulls
        FROM dwd_pull r GROUP BY r.dataset_id, r.gacha_type, r.item_id""")
