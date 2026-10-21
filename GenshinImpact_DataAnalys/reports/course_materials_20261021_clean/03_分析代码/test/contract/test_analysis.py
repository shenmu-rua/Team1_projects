"""分析连接的只读、列边界与主题交付契约；只用临时合成结构。"""

import sqlite3

import pytest

from genshin_insight.ads import analysis_connection


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM dim_item",
        "ATTACH DATABASE ':memory:' AS other",
        "PRAGMA query_only = OFF",
        "SELECT uid FROM dim_item",
        "SELECT value FROM secret",
        "CREATE TABLE unexpected (value)",
    ],
)
def test_analysis_connection_denies_identifiers_other_tables_and_writes(tmp_path, statement):
    database = tmp_path / "synthetic.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE dim_item (item_id, name, rank_type, uid)")
        connection.execute("CREATE TABLE secret (value)")
    with analysis_connection(database) as connection:
        assert connection.execute("SELECT name FROM dim_item").fetchall() == []
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute(statement)


def test_delivery_rejects_dual_axis_and_wrong_aspect(tmp_path):
    import matplotlib

    matplotlib.use("Agg")
    from genshin_insight import viz
    from theme.spec_check import SpecViolation

    viz.apply_theme(16)
    theme = viz.load_theme()
    fig = theme.canvas("ppt", width_in=16, height_in=9)
    viz.finish(
        fig,
        "合成验证包含5个聚合格",
        "仅测试，不交付",
        "测试合成数据；脚本 test_analysis；配置 test",
    )
    ax = theme.axes(fig)
    ax.twinx()
    with pytest.raises(SpecViolation):
        viz.save(fig, tmp_path / "forbidden.png")
    assert not (tmp_path / "forbidden.png").exists()
    theme.plt.close(fig)
    fig = theme.canvas("report")
    viz.finish(fig, "合成验证包含5个聚合格", "仅测试", "测试合成数据")
    with pytest.raises(ValueError, match="16:9"):
        viz.save(fig, tmp_path / "wrong_ratio.png", ppt=True)
    theme.plt.close(fig)
