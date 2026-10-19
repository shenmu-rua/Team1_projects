"""结构检查和本地清洗入口；帮助命令不会打开数据库。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from . import config
from .pipeline import clean_database, default_output_path
from .schema import inspect_schema, render_dictionary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="原神项目工具：结构检查与本地清洗。")
    commands = parser.add_subparsers(dest="command")
    schema_parser = commands.add_parser("schema", help="只读表名及列结构，禁止业务查询")
    schema_parser.add_argument("--database", type=Path, default=config.DB_PATH)
    schema_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    clean_parser = commands.add_parser("clean", help="只读源库，清洗并生成独立结果及聚合报告")
    clean_parser.add_argument("--database", type=Path, default=config.DB_PATH)
    clean_parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "clean":
        output = (args.output or default_output_path()).resolve()
        if not output.is_relative_to(config.PROJECT_ROOT.resolve()):
            parser.error("清洗产物必须位于本项目目录内部。")
        try:
            report = clean_database(
                args.database,
                output,
                progress=lambda stage: print(json.dumps({"stage": stage}), flush=True),
            )
        except (OSError, sqlite3.DatabaseError, ValueError, RuntimeError):
            parser.exit(2, "本地清洗未完成；源库未改写，未输出任何明细。\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    try:
        tables = inspect_schema(args.database)
    except (OSError, sqlite3.DatabaseError, ValueError) as error:
        parser.exit(2, f"表结构检查失败，已停止：{error}\n")
    if args.format == "json":
        result = {"access_mode": config.SCHEMA_ACCESS_MODE, "tables": [asdict(t) for t in tables]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_dictionary(tables))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
