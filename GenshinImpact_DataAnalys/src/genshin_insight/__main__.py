"""只提供表结构检查入口；帮助命令不会打开数据库。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from . import config
from .schema import inspect_schema, render_dictionary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="原神项目初始化工具：仅允许表结构检查。")
    commands = parser.add_subparsers(dest="command")
    schema_parser = commands.add_parser("schema", help="只读表名及列结构，禁止业务查询")
    schema_parser.add_argument("--database", type=Path, default=config.DB_PATH)
    schema_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        tables = inspect_schema(args.database)
    except (OSError, sqlite3.DatabaseError, ValueError) as error:
        parser.exit(2, f"表结构检查失败，已停止：{error}\n")
    if args.format == "json":
        result = {"access_mode": config.DATA_ACCESS_MODE, "tables": [asdict(t) for t in tables]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_dictionary(tables))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
