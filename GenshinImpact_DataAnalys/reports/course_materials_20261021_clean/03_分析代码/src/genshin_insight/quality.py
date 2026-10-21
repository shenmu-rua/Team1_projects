"""聚合对账与报告；不返回任何明细值、标识符或拒绝记录载荷。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def audit_cleaning(connection: sqlite3.Connection, input_rows: int) -> tuple[dict, list[dict]]:
    def scalar(statement: str) -> int:
        return int(connection.execute(statement).fetchone()[0] or 0)

    kept = scalar("SELECT count(*) FROM dwd_pull")
    rejected = scalar("SELECT count(*) FROM dwd_rejected_pull")
    reasons = dict(
        connection.execute(
            "SELECT reason, count(*) FROM dwd_rejected_pull GROUP BY reason ORDER BY reason"
        )
    )
    metrics = {
        "input_pulls": input_rows,
        "kept_pulls": kept,
        "rejected_pulls": rejected,
        "duplicate_rows_removed": sum(
            reasons.get(key, 0)
            for key in (
                "duplicate_provenance",
                "duplicate_gacha_id",
            )
        ),
        "conflicting_rows_quarantined": sum(
            reasons.get(key, 0)
            for key in (
                "conflicting_provenance",
                "conflicting_gacha_id",
            )
        ),
        "players_in_cleaned_pulls": scalar("SELECT count(DISTINCT player_id) FROM dwd_pull"),
        "timestamp_normalized_pulls": scalar("SELECT sum(time_normalized) FROM dwd_pull"),
        "sequence_changed_pulls": scalar("""SELECT count(*) FROM dwd_pull
            WHERE source_pool_seq IS NULL OR pool_seq != source_pool_seq"""),
        "item_type_review_pulls": scalar("SELECT sum(item_type_review) FROM dwd_pull"),
        "item_type_review_sources": scalar("""SELECT count(DISTINCT source_file_id)
            FROM dwd_pull WHERE item_type_review"""),
        "ambiguous_same_second_pulls": scalar("SELECT sum(time_order_ambiguous) FROM dwd_pull"),
        "preexisting_import_rejected_rows": scalar("SELECT count(*) FROM source.rejected_rows"),
        "rejection_reasons": reasons,
    }
    checks = []

    def check(name: str, actual: int, expected: int) -> None:
        checks.append(
            {"check": name, "actual": actual, "expected": expected, "passed": actual == expected}
        )

    check("input_row_accounting", kept + rejected, input_rows)
    check("rejection_reason_accounting", sum(reasons.values()), rejected)
    check(
        "accepted_rejected_overlap",
        scalar("""SELECT count(*) FROM dwd_pull p
        JOIN dwd_rejected_pull r ON r.pull_id = p.pull_id"""),
        0,
    )
    check("source_rows_staged", scalar("SELECT count(*) FROM stage_pull"), input_rows)
    check(
        "sequence_gaps",
        scalar("""SELECT count(*) FROM (
        SELECT player_id, pool_group FROM dwd_pull GROUP BY player_id, pool_group
        HAVING min(pool_seq) != 1 OR max(pool_seq) != count(*))"""),
        0,
    )
    for table in ("dws_player_pool", "dws_pool", "dws_daily", "dws_item"):
        check(f"{table}_total", scalar(f"SELECT coalesce(sum(pulls), 0) FROM {table}"), kept)
    for table in ("dws_player_pool", "dws_pool"):
        check(
            f"{table}_rank_accounting",
            scalar(f"SELECT count(*) FROM {table} WHERE star3 + star4 + star5 != pulls"),
            0,
        )
    check(
        "foreign_key_errors",
        int(connection.execute("PRAGMA main.foreign_key_check").fetchone() is not None),
        0,
    )
    connection.execute("""CREATE TABLE dq_check_result (
        check_id TEXT PRIMARY KEY, actual INTEGER NOT NULL,
        expected INTEGER NOT NULL, passed INTEGER NOT NULL CHECK(passed IN (0,1)))""")
    connection.executemany(
        "INSERT INTO dq_check_result VALUES (:check, :actual, :expected, :passed)", checks
    )
    if not all(item["passed"] for item in checks):
        failed = ", ".join(item["check"] for item in checks if not item["passed"])
        raise RuntimeError(f"清洗对账未通过：{failed}；不发布产物。")
    return metrics, checks


def write_reports(report: dict, database: Path) -> tuple[Path, Path]:
    json_path = database.with_suffix(".json")
    markdown_path = database.with_suffix(".md")
    with json_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    metrics = report["metrics"]
    lines = [
        "# 原神抽卡数据清洗报告",
        "",
        f"运行时间：{report['started_at']}；规则版本：{report['rule_version']}。",
        "",
        "仅本地程序处理明细。本报告只包含聚合稽核，未包含个人标识或明细示例。",
        "",
        "| 指标 | 数量 |",
        "| --- | ---: |",
        f"| 输入已导入抽卡记录 | {metrics['input_pulls']:,} |",
        f"| 清洗保留记录 | {metrics['kept_pulls']:,} |",
        f"| 移除或隔离记录 | {metrics['rejected_pulls']:,} |",
        f"| 其中确定重复 | {metrics['duplicate_rows_removed']:,} |",
        f"| 其中标识/来源冲突 | {metrics['conflicting_rows_quarantined']:,} |",
        f"| 保留记录涉及的内部账号 | {metrics['players_in_cleaned_pulls']:,} |",
        f"| 时间格式标准化 | {metrics['timestamp_normalized_pulls']:,} |",
        f"| 重新排序后序号变化 | {metrics['sequence_changed_pulls']:,} |",
        f"| 物品类型待复核记录 | {metrics['item_type_review_pulls']:,} |",
        f"| 物品类型待复核来源 | {metrics['item_type_review_sources']:,} |",
        f"| 含缺失 ID 的同秒排序存疑记录 | {metrics['ambiguous_same_second_pulls']:,} |",
        f"| 原导入阶段另行拒绝记录（不混入上述分母） | "
        f"{metrics['preexisting_import_rejected_rows']:,} |",
        "",
        "## 移除及隔离原因",
        "",
        "| 原因代码 | 数量 |",
        "| --- | ---: |",
    ]
    for reason, count in metrics["rejection_reasons"].items():
        lines.append(f"| {reason} | {count:,} |")
    if not metrics["rejection_reasons"]:
        lines.append("| 无 | 0 |")
    lines.extend(
        ["", "## 对账", "", "| 检查 | 实际 | 期望 | 结果 |", "| --- | ---: | ---: | --- |"]
    )
    for item in report["checks"]:
        lines.append(
            f"| {item['check']} | {item['actual']:,} | {item['expected']:,} | "
            f"{'通过' if item['passed'] else '失败'} |"
        )
    lines.extend(
        [
            "",
            "## 使用范围与限制",
            "",
            "- 原始库保持只读，所有被移除的记录仅在新库登记原 pull_id 和原因，可回查原库。",
            "- 清洗库不复制 UID、player_key、gacha_id、个人源路径、原始 JSON 或资源 BLOB。",
            "- 时间保留原始无时区墙钟口径，不推断时区；秒内无法确定的顺序已标记。",
            "- 类型编码存疑的来源整体标记 item_type_review=1；未猜测翻转类型或合并多语言名字。",
            "- 类型相关分析应排除待复核来源，或明确列为未核实；星级和物品身份保留原始语义。",
            "- 历史索引、预筛选直方图和旧 summary 未混入新汇总；原导入拒绝记录未重新解析。",
            "- DWD、DWS 均为本地分析层，含内部个人粒度；对外出图前另建 ADS 并落实小样本抑制。",
            "- 未实施首五星/末段截取、保底推断、跨数据集账号合并或按假定日期删除。",
            "",
            f"耗时：{report['elapsed_seconds']:.2f} 秒。",
            "",
        ]
    )
    with markdown_path.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    return json_path, markdown_path
