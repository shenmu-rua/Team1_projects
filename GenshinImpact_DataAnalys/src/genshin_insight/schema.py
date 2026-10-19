"""SQLite 表头检查；不查询、统计或抽样业务表。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class ColumnSchema:
    position: int
    name: str
    declared_type: str
    not_null: bool
    primary_key_position: int
    hidden: int


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: tuple[ColumnSchema, ...]


def _schema_authorizer(
    action: int,
    argument: str | None,
    detail: str | None,
    database: str | None,
    trigger: str | None,
) -> int:
    """仅放行表结构 PRAGMA 和 SQLite 内部结构读取，其他操作全部拒绝。"""
    if database not in (None, "main"):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA:
        if (argument or "").lower() in {"table_list", "table_info", "table_xinfo"}:
            return sqlite3.SQLITE_OK
    elif action == sqlite3.SQLITE_READ:
        if argument in {"sqlite_master", "sqlite_schema"}:
            return sqlite3.SQLITE_OK
    elif action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


@contextmanager
def _schema_connection(database: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(database).resolve(strict=True)
    if not path.is_file():
        raise ValueError("数据库路径必须是已经存在的文件。")
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.set_authorizer(_schema_authorizer)
        yield connection
    finally:
        connection.close()


def inspect_schema(database: str | Path) -> tuple[TableSchema, ...]:
    """返回普通主库表的列结构；跳过视图、虚拟表和 SQLite 内部表。"""
    with _schema_connection(database) as connection:
        names = sorted(
            row[1]
            for row in connection.execute("PRAGMA main.table_list")
            if row[0] == "main" and row[2] == "table" and not row[1].startswith("sqlite_")
        )
        tables = []
        for name in names:
            quoted_name = '"' + name.replace('"', '""') + '"'
            columns = tuple(
                ColumnSchema(
                    position=row[0],
                    name=row[1],
                    declared_type=row[2],
                    not_null=bool(row[3]),
                    primary_key_position=row[5],
                    hidden=row[6],
                )
                for row in connection.execute(f"PRAGMA main.table_xinfo({quoted_name})")
            )
            tables.append(TableSchema(name=name, columns=columns))
        return tuple(tables)


def _markdown_cell(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace("|", "&#124;")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def render_dictionary(tables: tuple[TableSchema, ...]) -> str:
    """渲染结构字典；不包含示例值、默认值、业务统计或推测的字段含义。"""
    lines = [
        "# 数据字典（仅表结构）",
        "",
        "访问范围：只读 SQLite 结构元信息；未读取业务数据行、样本、计数或聚合。",
        "只列普通表；视图、虚拟表及 SQLite 内部表不在本次范围。",
        "声明类型和 NOT NULL 是建表约束，不代表实际值类型或缺失情况。",
        "字段语义、记录粒度、关联关系、时间口径和清洗规则均待确认。",
        "主键序号 0 表示未声明主键；隐藏标记 0=普通列，2/3=生成列。",
        "默认值及其表达式不输出。",
        "",
    ]
    for table in tables:
        lines.extend(
            [
                f"## {_markdown_cell(table.name)}",
                "",
                "| 序号（从 0 起） | 字段 | 声明类型 | NOT NULL | 主键序号 | 隐藏标记 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for column in table.columns:
            lines.append(
                f"| {column.position} | {_markdown_cell(column.name)} | "
                f"{_markdown_cell(column.declared_type) or '未声明'} | "
                f"{'是' if column.not_null else '否'} | "
                f"{column.primary_key_position} | {column.hidden} |"
            )
        lines.append("")
    return "\n".join(lines)
