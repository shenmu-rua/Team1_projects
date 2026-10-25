"""大屏发布边界：只用合成聚合，不读取或连接真实数据库。"""

import json

import pytest

from genshin_insight import dashboard


@pytest.fixture
def release(tmp_path):
    """虚构DS03发布聚合；包含一个明确抑制月格。"""
    directory = tmp_path / "analysis"
    directory.mkdir()
    data = {
        "dataset": 3,
        "scope": {
            "dataset_id": 3,
            "pulls": 1000,
            "people": 20,
            "first_time": "2021-01-01 00:00:00",
            "last_time": "2021-02-28 23:59:59",
            "suppressed": False,
        },
        "provenance": {"config_version": "synthetic", "rule_version": "synthetic"},
        "checks": {"failed": 0, "checks": 3},
        "pools": [
            {"pool_group": pool, "pulls": 250, "people": 10, "star5": 5, "suppressed": False}
            for pool in (100, 200, 301, 302)
        ],
        "months": [
            {"pool_group": 301, "month": "2021-01", "pulls": 100, "people": 5, "suppressed": False},
            {
                "pool_group": 301,
                "month": "2021-02",
                "pulls": None,
                "people": None,
                "suppressed": True,
            },
        ],
        "clock": [{"weekday": 0, "hour": 0, "pulls": 1000, "people": 20, "suppressed": False}],
        "volume_bins": [{"lo": 1, "hi": None, "counts": {"0": 20}, "people": {"0": 20}}],
        "volume_median": 50,
        "rates": [
            {
                "pool_group": 301,
                "quartile": 1,
                "groups": 1,
                "people": 10,
                "q25": 1.0,
                "median": 2.0,
                "q75": 3.0,
            }
        ],
        "gap_bins": {"301": [{"lo": 1, "hi": None, "counts": {"301": 10}, "people": {"301": 5}}]},
        "gap_quality": {
            "player_pools": 10,
            "eligible_player_pools": 10,
            "ambiguous_pulls": 0,
            "item_type_review_pulls": 0,
        },
        "items": [{"name": "合成名称", "pulls": 10, "people": 5}],
        "privacy": {"minimum_people": 5, "people_semantics": "合成测试"},
    }

    def save():
        (directory / "ads.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    save()
    return directory, data, save


def test_projection_drops_unpublished_sections_and_identifier_fields(release):
    directory, data, save = release
    data["unpublished"] = {"uid": "synthetic-secret"}
    data["scope"]["uid"] = "synthetic-secret"
    data["items"][0]["source_path"] = "synthetic-secret"
    data["volume_bins"][0]["counts"]["uid"] = "synthetic-secret"
    save()
    safe = dashboard.load_aggregates(directory)
    assert "synthetic-secret" not in json.dumps(safe)
    assert safe["months"][1]["pulls"] is None
    assert safe["months"][1]["people"] is None


@pytest.mark.parametrize("violation", ["threshold", "small", "leak", "check", "dataset", "name"])
def test_unsafe_aggregate_cannot_be_published(release, violation):
    directory, data, save = release
    if violation == "threshold":
        data["privacy"]["minimum_people"] = 4
    elif violation == "small":
        data["items"][0]["people"] = 4
    elif violation == "leak":
        data["months"][1]["pulls"] = 1
    elif violation == "check":
        data["checks"]["failed"] = 1
    elif violation == "dataset":
        data["dataset"] = 2
    else:
        data["items"][0]["name"] = "synthetic-123456789"
    save()
    with pytest.raises(ValueError):
        dashboard.load_aggregates(directory)


def test_inconsistent_account_distribution_is_rejected(release):
    directory, data, save = release
    data["volume_bins"][0]["counts"]["0"] = 19
    save()
    with pytest.raises(ValueError, match="账号"):
        dashboard.load_aggregates(directory)


def test_build_stays_local_embeds_safely_and_never_connects_database(release, monkeypatch):
    import sqlite3

    from genshin_insight import defense

    directory, data, save = release
    data["items"][0]["name"] = "</script><script>synthetic-injection</script>"
    save()
    monkeypatch.setattr(dashboard.config, "PROJECT_ROOT", directory.parent)
    monkeypatch.setattr(
        dashboard,
        "theme_tokens",
        lambda: {
            **{f"pool-{pool}": "#c9668b" for pool in (100, 200, 301, 302)},
            "pink-light": "#fbe7ee",
            "pink": "#c9668b",
            "pink-dark": "#803a55",
        },
    )
    monkeypatch.setattr(defense, "embed_font", lambda text, path: ("c3ludGhldGlj", "SIL test"))

    def forbid_database(*args, **kwargs):
        raise AssertionError("Dashboard must not connect to a database")

    monkeypatch.setattr(sqlite3, "connect", forbid_database)
    output = dashboard.build(directory, directory.parent / "dashboard")
    html = (output / "index.html").read_text(encoding="utf-8")
    assert "\\u003c/script>\\u003cscript>synthetic-injection" in html
    assert "<script>synthetic-injection" not in html
    assert "__DATA__" not in html and "__FONT__" not in html
    assert "fetch(" not in html and "https://" not in html
    before = (output / "index.html").read_bytes()
    with pytest.raises(FileExistsError):
        dashboard.build(directory, output)
    assert (output / "index.html").read_bytes() == before
    dashboard.build(directory, output, replace=True)
    with pytest.raises(ValueError, match="本项目"):
        dashboard.build(directory, directory.parent.parent / "outside")


def test_replace_does_not_overwrite_unrelated_existing_directory(release, monkeypatch):
    directory, _, _ = release
    monkeypatch.setattr(dashboard.config, "PROJECT_ROOT", directory.parent)
    output = directory.parent / "unrelated"
    output.mkdir()
    sentinel = output / "user-work.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        dashboard.build(directory, output, replace=True)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_serve_refuses_to_expose_project_or_data(release, monkeypatch):
    directory, _, _ = release
    monkeypatch.setattr(dashboard.config, "PRESENTATION_DIR", directory.parent / "reports")
    (directory / "index.html").write_text("synthetic", encoding="utf-8")
    with pytest.raises(ValueError, match="reports"):
        dashboard.serve(directory)
