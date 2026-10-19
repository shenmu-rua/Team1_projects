"""清洗调度：只读源库、独立临时产物、对账通过后发布。"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from . import config
from .db import cleaning_connection
from .dims import build_dimensions
from .dwd import deduplicate, stage_pulls, write_details
from .dws import build_summaries
from .quality import audit_cleaning, write_reports


def default_output_path() -> Path:
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
    return config.DATA_DIR / f"genshin_clean_{timestamp}_{uuid4().hex[:8]}.db"


def clean_database(
    source: str | Path,
    output: str | Path,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """只输出聚合运行结果；拒绝覆盖任何已有目标或报告文件。"""
    source_path = Path(source).resolve(strict=True)
    output_path = Path(output).resolve()
    if not source_path.is_file():
        raise ValueError("源库必须是已经存在的文件。")
    if source_path == output_path:
        raise ValueError("清洗结果不得覆盖源库。")
    for path in (output_path, output_path.with_suffix(".json"), output_path.with_suffix(".md")):
        if path.exists():
            raise FileExistsError("清洗库或同名报告已经存在，请使用新输出名称。")
    source_stat = source_path.stat()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid4().hex}.partial")
    temporary.touch(exist_ok=False)
    started = time.monotonic()
    started_at = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    stage = "open_source"
    heartbeat = started

    def announce(name: str) -> None:
        nonlocal stage, heartbeat
        stage, heartbeat = name, time.monotonic()
        if progress:
            progress(name)

    def tick() -> int:
        nonlocal heartbeat
        if progress and time.monotonic() - heartbeat >= 20:
            progress(stage)
            heartbeat = time.monotonic()
        return 0

    try:
        with cleaning_connection(source_path, temporary) as connection:
            connection.set_progress_handler(tick, 1_000_000)
            connection.execute("BEGIN")
            announce("source_counts")
            input_rows = connection.execute("SELECT count(*) FROM source.pulls").fetchone()[0]
            announce("dimensions")
            build_dimensions(connection)
            announce("validate_details")
            stage_pulls(connection)
            announce("deduplicate")
            deduplicate(connection)
            announce("write_clean_details")
            write_details(connection)
            announce("rebuild_summaries")
            build_summaries(connection)
            announce("audit")
            metrics, checks = audit_cleaning(connection, input_rows)
            report = {
                "status": "success",
                "access_mode": config.DATA_ACCESS_MODE,
                "started_at": started_at,
                "config_version": config.CONFIG_VERSION,
                "rule_version": config.CLEANING_RULE_VERSION,
                "source_file_metadata": {
                    "size_bytes": source_stat.st_size,
                    "mtime_ns": source_stat.st_mtime_ns,
                },
                "metrics": metrics,
                "checks": checks,
            }
            connection.execute("""CREATE TABLE etl_run (
                run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL,
                config_version TEXT NOT NULL, rule_version TEXT NOT NULL,
                metrics_json TEXT NOT NULL)""")
            connection.execute(
                "INSERT INTO etl_run VALUES (?, ?, ?, ?, ?)",
                (
                    uuid4().hex,
                    started_at,
                    config.CONFIG_VERSION,
                    config.CLEANING_RULE_VERSION,
                    json.dumps(metrics, ensure_ascii=False),
                ),
            )
            connection.commit()
            announce("integrity_check")
            integrity_ok = all(
                row[0] == "ok" for row in connection.execute("PRAGMA main.quick_check")
            )
            if not integrity_ok:
                raise RuntimeError("清洗库完整性检查失败；不发布产物。")
            checks.append(
                {"check": "sqlite_quick_check", "actual": 1, "expected": 1, "passed": True}
            )
            connection.execute(
                "INSERT INTO dq_check_result VALUES (?, ?, ?, ?)",
                (
                    "sqlite_quick_check",
                    1,
                    1,
                    1,
                ),
            )
            connection.commit()
        current_stat = source_path.stat()
        if (current_stat.st_size, current_stat.st_mtime_ns) != (
            source_stat.st_size,
            source_stat.st_mtime_ns,
        ):
            raise RuntimeError("处理期间源库文件元信息变化；不发布产物。")
        announce("publish")
        # Windows 的 rename 拒绝已有目标；其他平台用硬链接保证不覆盖。
        if os.name == "nt":
            temporary.rename(output_path)
        else:
            os.link(temporary, output_path)
            temporary.unlink()
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report["database"] = str(output_path)
        announce("reports")
        report_json, report_markdown = write_reports(report, output_path)
        report["report_json"] = str(report_json)
        report["report_markdown"] = str(report_markdown)
        announce("complete")
        return report
    except (sqlite3.DatabaseError, OSError, ValueError, RuntimeError):
        # 错误只抛出固定阶段名，避免 SQLite/回调异常夹带源记录值。
        raise RuntimeError(f"清洗在 {stage} 阶段停止；源库未改写。") from None
    finally:
        if temporary.exists():
            temporary.unlink()
