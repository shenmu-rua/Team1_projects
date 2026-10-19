"""时间规则的合成边界，不使用真实记录。"""

import pytest

from genshin_insight.dwd import normalize_time


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2020-02-29 12:34:56", "2020-02-29 12:34:56"),
        (" 2022-01-01T00:00:00\n", "2022-01-01 00:00:00"),
        ("2021-02-29 00:00:00", None),
        ("2022-02-30 00:00:00", None),
        ("2022-01-01 00:00:60", None),
        ("2022-01-01 00:00:00+08:00", None),
        ("2022-01-01 00:00:00.123", None),
        ("20220101T000000", None),
        (None, None),
        (123, None),
        ("", None),
    ],
)
def test_time_normalization(value, expected):
    assert normalize_time(value) == expected
