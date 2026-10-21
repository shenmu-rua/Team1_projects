"""访问契约：只允许元信息，禁止空表上的明细、聚合与写入 SQL。"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from genshin_insight import config
from genshin_insight.__main__ import main
from genshin_insight.schema import _schema_connection


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM empty_table",
        "SELECT field FROM empty_table LIMIT 0",
        "SELECT COUNT(*) FROM empty_table",
        "SELECT MAX(field) FROM empty_table",
        "UPDATE empty_table SET field = NULL",
        "DELETE FROM empty_table",
        "CREATE TABLE unexpected (field TEXT)",
        "DROP TABLE empty_table",
        "ATTACH DATABASE ':memory:' AS other",
        "PRAGMA query_only = OFF",
        "PRAGMA page_count",
    ],
)
def test_non_schema_queries_are_denied(tmp_path, statement):
    database = tmp_path / "access.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE empty_table (field TEXT)")
    with _schema_connection(database) as connection:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute(statement)


def test_help_never_opens_database(monkeypatch, capsys):
    def denied_connection(*args, **kwargs):
        raise AssertionError("帮助命令不应连接数据库")

    monkeypatch.setattr(sqlite3, "connect", denied_connection)
    assert main([]) == 0
    assert "schema" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["schema", "clean", "charts", "defense", "opener", "report"])
def test_all_subcommand_help_is_available_without_database_access(monkeypatch, capsys, command):
    def denied_connection(*args, **kwargs):
        raise AssertionError("帮助命令不应连接数据库")

    monkeypatch.setattr(sqlite3, "connect", denied_connection)
    with pytest.raises(SystemExit) as stopped:
        main([command, "--help"])
    assert stopped.value.code == 0
    assert "--help" in capsys.readouterr().out


def test_imports_do_not_connect_read_files_create_directories_or_load_matplotlib():
    project_root = config.PROJECT_ROOT
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join([str(project_root / "src"), str(project_root)])
    script = """
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

def denied(*args, **kwargs):
    raise AssertionError('Import must be passive')

with patch.object(sqlite3, 'connect', denied), patch.object(Path, 'open', denied), \\
     patch.object(Path, 'mkdir', denied), patch.object(Path, 'read_text', denied):
    import genshin_insight
    import genshin_insight.config
    import genshin_insight.schema
    import genshin_insight.viz
    import genshin_insight.__main__
    import genshin_insight.ads
    import genshin_insight.charts
    import genshin_insight.defense
    import genshin_insight.speech
    import genshin_insight.opener
    import genshin_insight.report
    import genshin_insight.viz.report_plots
    import genshin_insight.viz.plots
    import theme
assert not any(name.startswith('matplotlib') for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(project_root),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
