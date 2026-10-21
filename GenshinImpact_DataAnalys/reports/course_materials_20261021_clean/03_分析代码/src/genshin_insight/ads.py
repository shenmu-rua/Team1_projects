"""只读清洗库，发布可直接作图的聚合；账号级中间结果不离开本模块。"""

from __future__ import annotations

import re
import sqlite3
from bisect import bisect_left
from contextlib import contextmanager
from pathlib import Path
from statistics import median

POOL_NAMES = {100: "新手祈愿", 200: "常驻祈愿", 301: "角色活动祈愿", 302: "武器活动祈愿"}
MIN_PEOPLE = 5
READ_COLUMNS = {
    "dim_item": {"item_id", "name", "rank_type"},
    "dwd_pull": {"player_id", "dataset_id", "item_id", "pool_group", "pool_seq", "gacha_time"},
    "dws_daily": {"dataset_id", "pull_date", "pool_group", "pulls", "players"},
    "dws_item": {"dataset_id", "item_id", "pulls", "players"},
    "dws_player_pool": {
        "player_id",
        "dataset_id",
        "pool_group",
        "pulls",
        "star3",
        "star4",
        "star5",
        "first_time",
        "last_time",
        "ambiguous_order_pulls",
        "item_type_review_pulls",
    },
    "dq_check_result": {"passed"},
    "etl_run": {"config_version", "rule_version"},
}


@contextmanager
def analysis_connection(path: Path):
    """禁止写入、附加库和无关列；仅在显式调用时连接。"""
    path = Path(path).resolve(strict=True)
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA temp_store = FILE")
        connection.row_factory = sqlite3.Row

        def authorize(action, table, column, database, trigger):
            if action == sqlite3.SQLITE_READ:
                return (
                    sqlite3.SQLITE_OK
                    if column in READ_COLUMNS.get(table, ())
                    else sqlite3.SQLITE_DENY
                )
            if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and column not in {
                "load_extension",
                "readfile",
                "writefile",
            }:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        connection.set_authorizer(authorize)
        yield connection
    finally:
        connection.close()


def suppress(rows: list[dict], measures: tuple[str, ...], people: str = "people") -> list[dict]:
    """分区内主抑制与互补抑制；所有隐藏格同标记，连贡献人数也不发布。"""
    hidden = {i for i, row in enumerate(rows) if row[people] < MIN_PEOPLE}
    if len(hidden) == 1 and len(rows) > 1:
        hidden.add(
            min((i for i in range(len(rows)) if i not in hidden), key=lambda i: rows[i][people])
        )
    return [
        {**row, **dict.fromkeys((*measures, people), None), "suppressed": True}
        if i in hidden
        else {**row, "suppressed": False}
        for i, row in enumerate(rows)
    ]


def coarsen(rows: list[dict], series: tuple[int, ...], disjoint: bool = False) -> list[dict]:
    """共同合并相邻箱，直到每系列每箱的贡献人数下界≥5；不累加重叠人数。"""
    rows = [{**row, "counts": dict(row["counts"]), "people": dict(row["people"])} for row in rows]
    while len(rows) > 1:
        small = next(
            (i for i, row in enumerate(rows) if any(row["people"][s] < MIN_PEOPLE for s in series)),
            None,
        )
        if small is None:
            break
        left = small - 1 if small == len(rows) - 1 else small
        a, b = rows[left : left + 2]
        rows[left : left + 2] = [
            {
                "lo": a["lo"],
                "hi": b["hi"],
                "counts": {s: a["counts"][s] + b["counts"][s] for s in series},
                "people": {
                    s: a["people"][s] + b["people"][s]
                    if disjoint
                    else max(a["people"][s], b["people"][s])
                    for s in series
                },
            }
        ]
    if any(row["people"][s] < MIN_PEOPLE for row in rows for s in series):
        return []
    return rows


def collect(path: Path, dataset: int = 3, progress=lambda stage: None) -> dict:
    """只返回经保护的 ADS；不同来源不合并账号，不打印任何账号级数据。"""
    import numpy as np
    import pandas as pd

    with analysis_connection(path) as connection:

        def query(sql, parameters=()):
            return [dict(row) for row in connection.execute(sql, parameters)]

        checks = query(
            "SELECT SUM(passed = 0) AS failed, COUNT(passed) AS checks FROM dq_check_result"
        )[0]
        if not checks["checks"] or checks["failed"]:
            raise ValueError("清洗稽核未通过，停止分析。")
        provenance = query("SELECT config_version, rule_version FROM etl_run")[0]
        cohorts = query("""SELECT dataset_id, SUM(pulls) AS pulls, COUNT(DISTINCT player_id) AS people,
            MIN(first_time) AS first_time, MAX(last_time) AS last_time
            FROM dws_player_pool GROUP BY dataset_id""")
        cohorts = suppress(cohorts, ("pulls", "first_time", "last_time"))
        scope = next(
            (row for row in cohorts if row["dataset_id"] == dataset and not row["suppressed"]), None
        )
        if scope is None:
            raise ValueError("目标数据集不存在或未达到聚合发布门槛。")
        pools = query(
            """SELECT pool_group, SUM(pulls) AS pulls, COUNT(player_id) AS people,
            SUM(star5) AS star5, SUM(star5 > 0) AS star5_people
            FROM dws_player_pool WHERE dataset_id = ? GROUP BY pool_group""",
            (dataset,),
        )
        if any(row["pool_group"] not in POOL_NAMES for row in pools):
            raise ValueError("出现未配置卡池，需要补全固定名称与颜色映射。")
        pools = suppress(pools, ("pulls", "star5", "star5_people"))
        star5 = suppress(
            [
                {
                    "pool_group": row["pool_group"],
                    "people": row["star5_people"] or 0,
                    "star5": row["star5"],
                }
                for row in pools
            ],
            ("star5",),
        )
        for row, five in zip(pools, star5, strict=True):
            row["star5"] = five["star5"]
            row.pop("star5_people")
        progress("月度聚合")
        months = query(
            """SELECT SUBSTR(pull_date, 1, 7) AS month, pool_group,
            SUM(pulls) AS pulls, MAX(players) AS people
            FROM dws_daily WHERE dataset_id = ? GROUP BY month, pool_group""",
            (dataset,),
        )
        if sum(row["pulls"] for row in months) != scope["pulls"]:
            raise RuntimeError("月度聚合对账失败。")
        months = [
            row
            for pool in POOL_NAMES
            for row in suppress([row for row in months if row["pool_group"] == pool], ("pulls",))
        ]
        progress("星期与小时聚合")
        clock = query(
            """SELECT (CAST(STRFTIME('%w', gacha_time) AS INTEGER) + 6) % 7 AS weekday,
            CAST(STRFTIME('%H', gacha_time) AS INTEGER) AS hour, COUNT(player_id) AS pulls,
            COUNT(DISTINCT player_id) AS people FROM dwd_pull
            WHERE dataset_id = ? GROUP BY weekday, hour""",
            (dataset,),
        )
        if sum(row["pulls"] for row in clock) != scope["pulls"]:
            raise RuntimeError("时间矩阵聚合对账失败。")
        clock = suppress(clock, ("pulls",))
        progress("账号记录量与分层分布")
        volumes = [
            row["pulls"]
            for row in query(
                """SELECT SUM(pulls) AS pulls FROM dws_player_pool
            WHERE dataset_id = ? GROUP BY player_id""",
                (dataset,),
            )
        ]
        bounds = [100, 300, 600, 1000, 2000, 5000, None]
        bins = [
            {
                "lo": (bounds[i - 1] or 0) + 1 if i else 1,
                "hi": hi,
                "counts": {0: 0},
                "people": {0: 0},
            }
            for i, hi in enumerate(bounds)
        ]
        for value in volumes:
            bucket = bins[bisect_left(bounds[:-1], value)]
            bucket["counts"][0] += 1
            bucket["people"][0] += 1
        volume_bins = coarsen(bins, (0,), disjoint=True)
        rates = []
        for pool in POOL_NAMES:
            values = query(
                """SELECT pulls, star5 FROM dws_player_pool
                WHERE dataset_id = ? AND pool_group = ?""",
                (dataset, pool),
            )
            if len(values) < MIN_PEOPLE:
                continue
            frame = pd.DataFrame(values)
            frame["quartile"] = pd.qcut(frame.pulls, 4, labels=False, duplicates="drop")
            groups = int(frame["quartile"].nunique())
            grouped = list(frame.groupby("quartile"))
            if any(len(part) < MIN_PEOPLE for _, part in grouped):
                continue
            for group, part in grouped:
                if len(part) >= MIN_PEOPLE:
                    q25, mid, q75 = np.percentile(100 * part.star5 / part.pulls, [25, 50, 75])
                    rates.append(
                        {
                            "pool_group": pool,
                            "quartile": int(group) + 1,
                            "groups": groups,
                            "people": len(part),
                            "q25": q25,
                            "median": mid,
                            "q75": q75,
                        }
                    )
        progress("记录内相邻五星间隔聚合")
        intervals = query(
            """WITH five AS (
            SELECT p.pool_group, p.player_id, p.pool_seq - LAG(p.pool_seq) OVER
                (PARTITION BY p.player_id, p.pool_group ORDER BY p.pool_seq) AS gap
            FROM dwd_pull p JOIN dim_item i ON i.item_id = p.item_id
            JOIN dws_player_pool s ON s.player_id = p.player_id AND s.pool_group = p.pool_group
            WHERE p.dataset_id = ? AND i.rank_type = 5 AND s.ambiguous_order_pulls = 0
                AND p.pool_group IN (200, 301, 302))
            SELECT pool_group, gap, COUNT(player_id) AS intervals,
                COUNT(DISTINCT player_id) AS people FROM five WHERE gap IS NOT NULL
            GROUP BY pool_group, gap""",
            (dataset,),
        )
        gap_bounds = [*range(10, 101, 10), 150, None]
        gap_bins = [
            {
                "lo": gap_bounds[i - 1] + 1 if i else 1,
                "hi": hi,
                "counts": dict.fromkeys((200, 301, 302), 0),
                "people": dict.fromkeys((200, 301, 302), 0),
            }
            for i, hi in enumerate(gap_bounds)
        ]
        for row in intervals:
            bucket = gap_bins[bisect_left(gap_bounds[:-1], row["gap"])]
            pool = row["pool_group"]
            bucket["counts"][pool] += row["intervals"]
            bucket["people"][pool] = max(bucket["people"][pool], row["people"])
        gap_bins = {
            pool: coarsen(
                [
                    {
                        "lo": row["lo"],
                        "hi": row["hi"],
                        "counts": {pool: row["counts"][pool]},
                        "people": {pool: row["people"][pool]},
                    }
                    for row in gap_bins
                ],
                (pool,),
            )
            for pool in (200, 301, 302)
        }
        quality = query(
            """SELECT COUNT(player_id) AS player_pools,
            SUM(ambiguous_order_pulls = 0) AS eligible_player_pools,
            SUM(ambiguous_order_pulls) AS ambiguous_pulls,
            SUM(item_type_review_pulls) AS item_type_review_pulls FROM dws_player_pool
            WHERE dataset_id = ? AND pool_group IN (200, 301, 302)""",
            (dataset,),
        )[0]
        progress("五星原始名称聚合")
        items = query(
            """SELECT i.name, SUM(s.pulls) AS pulls, MAX(s.players) AS people
            FROM dws_item s JOIN dim_item i ON i.item_id = s.item_id
            WHERE s.dataset_id = ? AND i.rank_type = 5 GROUP BY i.name""",
            (dataset,),
        )
        items = sorted(
            (
                row
                for row in items
                if row["people"] >= MIN_PEOPLE and not re.search(r"\d{8,}", row["name"])
            ),
            key=lambda row: row["pulls"],
            reverse=True,
        )[:12]
        if sum(volumes) != scope["pulls"] or sum(row["counts"][0] for row in volume_bins) != len(
            volumes
        ):
            raise RuntimeError("账号分布聚合对账失败。")
        return {
            "dataset": dataset,
            "scope": scope,
            "provenance": provenance,
            "checks": checks,
            "cohorts": cohorts,
            "pools": pools,
            "months": months,
            "clock": clock,
            "volume_bins": volume_bins,
            "volume_median": median(volumes),
            "rates": rates,
            "gap_bins": gap_bins,
            "gap_quality": quality,
            "items": items,
            "privacy": {
                "minimum_people": MIN_PEOPLE,
                "people_semantics": "months/items/gap_bins 为贡献人数保守下界；其余为对应聚合内去重账号数",
            },
        }
