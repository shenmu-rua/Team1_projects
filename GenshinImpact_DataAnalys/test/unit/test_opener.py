"""开场视频的指标对账和隐私保护，仅使用明确合成汇总。"""

from copy import deepcopy

import pytest

from genshin_insight import opener
from genshin_insight.opener import SCENES, summarize, video_timing


def synthetic():
    return {
        "scope": {
            "pulls": 1000,
            "people": 20,
            "first_time": "2022-01-01",
            "last_time": "2022-02-28",
        },
        "pools": [
            {"pool_group": 301, "pulls": 800, "people": 20},
            {"pool_group": 200, "pulls": 200, "people": 10},
        ],
        "months": [
            {"pool_group": 301, "month": "2022-01", "pulls": 100, "people": 10},
            {"pool_group": 301, "month": "2022-02", "pulls": 700, "people": 15},
            {
                "pool_group": 301,
                "month": "2022-03",
                "pulls": None,
                "people": None,
                "suppressed": True,
            },
        ],
        "volume_median": 50,
        "volume_bins": [{"lo": 1, "hi": None, "counts": {0: 20}, "people": {0: 20}}],
        "items": [{"name": "合成角色甲", "pulls": 25, "people": 10}],
    }


def test_safe_totals_peaks_and_gaps_without_mutating_input():
    data = synthetic()
    before = deepcopy(data)
    result = summarize(data)
    assert result["roleShare"] == 80
    assert result["peak"] == {"month": "2022-02", "count": 700}
    assert result["months"][-1]["count"] is None
    assert result["items"] == [{"name": "合成角色甲", "count": 25}]
    assert data == before


@pytest.mark.parametrize("section", ["scope", "pools"])
def test_unprotected_small_groups_are_rejected(section):
    data = synthetic()
    target = data[section] if section == "scope" else data[section][0]
    target["people"] = 4
    with pytest.raises(ValueError, match="门槛|隐藏"):
        summarize(data)


def test_inconsistent_total_is_rejected():
    data = synthetic()
    data["scope"]["pulls"] += 1
    with pytest.raises(ValueError, match="不一致"):
        summarize(data)


def test_video_timeline_keeps_all_scenes_and_a_clear_white_tail():
    timing = video_timing()
    assert SCENES[-1][1] == timing["graphicsDuration"] == 40
    assert timing["sourceEnd"] - timing["sourceStart"] == pytest.approx(timing["duration"])
    assert timing["fadeStart"] < timing["graphicsDuration"] < timing["whiteAt"] < timing["duration"]
    assert timing["duration"] - timing["graphicsDuration"] == pytest.approx(1.2)
    assert timing["fps"] == 60


@pytest.mark.parametrize("source_end", [float("nan"), float("inf"), -1, 40])
def test_video_cut_rejects_an_endpoint_without_room_for_the_full_timeline(source_end):
    with pytest.raises(ValueError, match="结束时间"):
        video_timing(source_end)


@pytest.mark.parametrize("prepare_only", [False, True])
def test_build_keeps_intermediate_media_out_of_the_delivery_folder(
    tmp_path, monkeypatch, prepare_only
):
    monkeypatch.setattr(opener.config, "PROJECT_ROOT", tmp_path)
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "ads.json").write_text('{"synthetic":true}', encoding="utf-8")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"synthetic source video")
    data = synthetic() | {"dataset": 3}
    monkeypatch.setattr(
        opener,
        "load_release",
        lambda path: (
            data,
            {"rule_version": "test"},
            {"settings": {"version": "test"}, "config_hash": "test"},
        ),
    )

    def prepare_video(source, target, timing, ffmpeg):
        target.write_bytes(b"synthetic trimmed video")

    def embed_font(html, target):
        target.write_bytes(b"synthetic font")
        (target.parent / "FONT_LICENSE.txt").write_text("Synthetic license", encoding="utf-8")
        return "synthetic-font", "Synthetic license"

    def render(output, ffmpeg, node, work):
        assert work.is_relative_to(tmp_path / ".pytest_cache")
        assert (work / "motion.html").is_file()
        assert (work / "assets/background.mp4").is_file()
        (output / "开场视频.mp4").write_bytes(b"synthetic final video")

    monkeypatch.setattr(opener, "prepare_video", prepare_video)
    monkeypatch.setattr(opener, "embed_font", embed_font)
    monkeypatch.setattr(opener, "render", render)
    output = tmp_path / "delivery"
    result = opener.build(
        analysis, output, source, ffmpeg="synthetic-ffmpeg", prepare_only=prepare_only
    )
    assert not (output / "motion.html").exists()
    assert not (output / "assets/background.mp4").exists()
    assert {path.name for path in (output / "assets").iterdir()} == {"FONT_LICENSE.txt"}
    if prepare_only:
        assert result.is_relative_to(tmp_path / ".pytest_cache") and result.is_file()
    else:
        assert result == output / "index.html" and result.is_file()
        assert list((tmp_path / ".pytest_cache").iterdir()) == []
