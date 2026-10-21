"""检验小样本不能由总数补回，以及重叠贡献账号不能按格相加。"""

from genshin_insight.ads import coarsen, suppress


def test_complementary_suppression_hides_all_measures_and_people():
    rows = [
        {"key": i, "people": n, "pulls": n * 100, "star5": n} for i, n in enumerate([3, 12, 20])
    ]
    released = suppress(rows, ("pulls", "star5"))
    assert sum(row["suppressed"] for row in released) == 2
    assert all(row["pulls"] is row["star5"] is row["people"] is None for row in released[:2])
    assert released[2]["pulls"] == 2000
    assert rows[0]["people"] == 3


def test_two_primary_cells_do_not_need_another_secondary_cell():
    released = suppress([{"people": n, "pulls": n * 100} for n in [1, 4, 20]], ("pulls",))
    assert [row["suppressed"] for row in released] == [True, True, False]


def test_merging_counts_never_sums_potentially_overlapping_people():
    rows = [{"lo": i, "hi": i, "counts": {301: 100}, "people": {301: 3}} for i in [1, 2]]
    assert coarsen(rows, (301,)) == []
    assert rows[0]["counts"][301] == 100


def test_common_bins_preserve_every_series_count_and_open_tail():
    rows = [
        {"lo": 1, "hi": 10, "counts": {200: 10, 301: 20}, "people": {200: 6, 301: 2}},
        {"lo": 11, "hi": None, "counts": {200: 30, 301: 40}, "people": {200: 1, 301: 9}},
    ]
    assert coarsen(rows, (200, 301)) == [
        {"lo": 1, "hi": None, "counts": {200: 40, 301: 60}, "people": {200: 6, 301: 9}}
    ]


def test_disjoint_account_bins_can_add_people_safely():
    rows = [{"lo": i, "hi": i, "counts": {0: 3}, "people": {0: 3}} for i in [1, 2]]
    assert coarsen(rows, (0,), disjoint=True) == [
        {"lo": 1, "hi": 2, "counts": {0: 6}, "people": {0: 6}}
    ]
