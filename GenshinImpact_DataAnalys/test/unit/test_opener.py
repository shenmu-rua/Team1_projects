"""开场视频的指标对账和隐私保护，仅使用明确合成汇总。"""

from copy import deepcopy

import pytest

from genshin_insight.opener import summarize


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
