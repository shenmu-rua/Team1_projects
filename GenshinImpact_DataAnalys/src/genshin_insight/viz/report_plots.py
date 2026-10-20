"""A4报告图表：同次发布ADS，15.4厘米版心，刻度实际字号不小于8磅。"""

from __future__ import annotations

from pathlib import Path

from ..ads import POOL_NAMES
from . import finish, load_theme, save, sequential_cmap
from .plots import bin_label, pool_colors


def register_fonts(cache: Path):
    """把可变开源字体定为常规与粗体，避免绘图引擎误取最细字重。"""
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    from matplotlib import font_manager

    source = str(font_manager.findfont(font_manager.FontProperties(family="Noto Sans SC")))
    with TTFont(source) as original:
        if "fvar" not in original:
            return
        cache.mkdir(parents=True, exist_ok=True)
        for weight in (400, 700):
            target = cache / f"NotoSansSC-{weight}.ttf"
            if not target.exists():
                font = instantiateVariableFont(original, {"wght": weight}, updateFontNames=True)
                font.save(target)
                font.close()
            font_manager.fontManager.addfont(str(target))


def generate(data: dict, output: Path, version: str) -> list[Path]:
    """按报告物理宽度重新排图，保持卡池颜色与全部统计口径。"""
    import matplotlib

    matplotlib.use("Agg")
    import numpy as np
    from matplotlib import pyplot as plt
    from matplotlib.colors import LogNorm

    from . import apply_theme

    register_fonts(output / ".font-cache")
    apply_theme(10)
    theme, colors = load_theme(), pool_colors()
    plt.rcParams.update({"font.size": 8.5, "axes.labelsize": 8.5})
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    source = (
        f"来源：原神留存抽卡记录 主分析03\n制作：genshin-insight report  图表{version}  清洗1.0.0"
    )

    def page(title, subtitle, height=5.0):
        fig = plt.figure(figsize=(15.4 / 2.54, height), facecolor=theme.BG)
        finish(fig, title, subtitle, source)
        for text in fig.texts:
            text.set_fontsize(12 if text is fig.texts[0] else 8.5 if text is fig.texts[1] else 8)
        fig.texts[0].set_position((0.075, 0.95))
        fig.texts[1].set_position((0.075, 0.895))
        return fig

    def axis(fig, rect, title, grid="x"):
        ax = theme.axes(fig, rect=rect, grid=grid)
        ax.tick_params(labelsize=8.5)
        ax.text(0, 1.04, title, transform=ax.transAxes, size=9.5, color=theme.INK, weight="bold")
        return ax

    def hbars(ax, labels, values, palette, formatter, unit, scale=None):
        peak = scale or max(values)
        ax.set(xlim=(-peak * 0.75, peak * 1.45), ylim=(-0.65, len(labels) - 0.35), yticks=[])
        positions = list(reversed(range(len(labels))))
        theme.label_column(ax, list(zip(positions, labels, strict=True)), 0, -peak * 0.04, size=8.5)
        for y, value, color in zip(positions, values, palette, strict=True):
            theme.hbar(ax, y, 0, value, 8, color)
            theme.value_label(ax, value, y, formatter(value), theme.INK, size=8.5)
        ax.set_xticks([0, peak / 2, peak], [f"{v:,.1f}" for v in (0, peak / 2, peak)])
        ax.set_xlabel(unit, fontsize=8.5)

    def publish(fig, code):
        paths.append(save(fig, output / f"{code}.png"))
        plt.close(fig)

    pools = sorted(data["pools"], key=lambda row: row["pulls"], reverse=True)
    share = 100 * pools[0]["pulls"] / data["scope"]["pulls"]
    fig = page(f"角色活动祈愿占留存抽数{share:.1f}%", "301/400合并；抽数与五星占比使用上下独立面板")
    for rect, key in [((0.075, 0.52, 0.85, 0.25), "pulls"), ((0.075, 0.17, 0.85, 0.25), "rate")]:
        values = [
            row["pulls"] / 10000 if key == "pulls" else 100 * row["star5"] / row["pulls"]
            for row in pools
        ]
        hbars(
            axis(fig, rect, "各池留存抽数" if key == "pulls" else "记录内五星占比"),
            [POOL_NAMES[row["pool_group"]] for row in pools],
            values,
            [colors[row["pool_group"]] for row in pools],
            lambda value: f"{value:,.1f}" if key == "pulls" else f"{value:.2f}%",
            "万抽" if key == "pulls" else "占本池留存抽数的百分比",
        )
    publish(fig, "A01")

    peak = max(
        (row for row in data["months"] if row["pulls"] is not None), key=lambda row: row["pulls"]
    )
    fig = page(
        f"{peak['month']}单池月记录达{peak['pulls'] / 10000:.1f}万抽",
        "自然月汇总；各池纵轴独立；缺口不插值；时区未知",
    )
    months = sorted({row["month"] for row in data["months"]})
    for i, pool in enumerate(POOL_NAMES):
        ax = axis(
            fig, (0.075 + i % 2 * 0.46, 0.55 - i // 2 * 0.35, 0.38, 0.22), POOL_NAMES[pool], "y"
        )
        lookup = {row["month"]: row["pulls"] for row in data["months"] if row["pool_group"] == pool}
        values = np.array(
            [
                lookup.get(month) / 10000 if lookup.get(month) is not None else np.nan
                for month in months
            ]
        )
        ax.plot(values, color=colors[pool], marker=".", linewidth=1.4, markersize=3)
        ax.set(ylim=(0, max(1, np.nanmax(values) * 1.3)), ylabel="万抽")
        indexes = [0, len(months) // 2, len(months) - 1]
        ax.set_xticks(indexes, [months[index][2:] for index in indexes])
        j = int(np.nanargmax(values))
        ax.annotate(
            f"{values[j]:,.1f}",
            (j, values[j]),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            size=8.5,
            color=colors[pool],
        )
    publish(fig, "A02")

    peak = max(
        (row for row in data["clock"] if row["pulls"] is not None), key=lambda row: row["pulls"]
    )
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    fig = page(
        f"{weekdays[peak['weekday']]}{peak['hour']}时累计{peak['pulls'] / 10000:.1f}万抽",
        "上下两面板分别为00—11时、12—23时\n格内单位为万抽；同一对数色阶；时区及曝光天数未知",
        5.2,
    )
    matrix = np.full((7, 24), np.nan)
    for row in data["clock"]:
        if row["pulls"] is not None:
            matrix[row["weekday"], row["hour"]] = row["pulls"] / 10000
    norm = LogNorm(float(np.nanmin(matrix)), float(np.nanmax(matrix)))
    cmap = sequential_cmap()
    cmap.set_bad(theme.GRAY)
    for part in range(2):
        ax = axis(fig, (0.075, 0.54 - part * 0.35, 0.75, 0.25), "", None)
        mesh = ax.imshow(
            matrix[:, part * 12 : (part + 1) * 12],
            aspect="auto",
            cmap=cmap,
            norm=norm,
            extent=(0, 12, 6.5, -0.5),
        )
        ax.set(xlim=(-1, 12), ylim=(6.5, -0.5), yticks=[])
        ax.set_xticks(
            np.arange(12) + 0.5, [f"{hour:02}" for hour in range(part * 12, (part + 1) * 12)]
        )
        theme.label_column(ax, list(enumerate(weekdays)), 0, -0.12, size=8.5)
        for day in range(7):
            for hour in range(12):
                value = matrix[day, hour + part * 12]
                label = (
                    "抑制"
                    if not np.isfinite(value)
                    else f"{value:.2f}"
                    if value < 0.1
                    else f"{value:.1f}"
                )
                ax.text(
                    hour + 0.5,
                    day,
                    label,
                    ha="center",
                    va="center",
                    fontsize=8,
                    color=theme.BG if np.isfinite(value) and norm(value) > 0.65 else theme.INK,
                )
    cax = fig.add_axes((0.875, 0.19, 0.025, 0.60))
    cb = fig.colorbar(mesh, cax=cax)
    ticks = np.geomspace(norm.vmin, norm.vmax, 4)
    cb.set_ticks(ticks, labels=[f"{value:.2f}" for value in ticks])
    cb.ax.tick_params(labelsize=8, length=0)
    publish(fig, "A03")

    bins = data["volume_bins"]
    counts = [row["counts"][0] for row in bins]
    fig = page(
        f"账号留存抽数中位数为{data['volume_median']:,.0f}抽",
        "账号内合并各池；上下为分箱分布与分箱累计分布",
        5.8,
    )
    hbars(
        axis(fig, (0.075, 0.49, 0.85, 0.30), "账号分箱占比"),
        [bin_label(row) for row in bins],
        [100 * n / sum(counts) for n in counts],
        [theme.MAIN] * len(bins),
        lambda value: f"{value:.1f}%",
        "占全部账号的百分比",
    )
    ax = axis(fig, (0.20, 0.16, 0.72, 0.22), "各箱上界内累计账号占比", "y")
    cdf = 100 * np.cumsum(counts) / sum(counts)
    ax.plot(cdf, marker="o", markersize=3.5, color=theme.MAIN)
    for i, value in enumerate(cdf):
        ax.annotate(
            f"{value:.1f}",
            (i, value),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            size=8,
        )
    ax.set_xticks(
        range(len(bins)), [f"≤{row['hi']:,}" if row["hi"] else "全部" for row in bins], rotation=25
    )
    ax.set(ylim=(0, 118), ylabel="累计账号占比 %")
    publish(fig, "A04")

    role = [row for row in data["rates"] if row["pool_group"] == 301]
    q4 = max(role, key=lambda row: row["quartile"])
    fig = page(
        f"角色池Q4组五星占比中位数{q4['median']:.2f}%",
        "账号等权；点为P50，线为P25至P75；不是置信区间",
        5.2,
    )
    upper = max(row["q75"] for row in data["rates"]) * 1.3
    for i, pool in enumerate(POOL_NAMES):
        ax = axis(
            fig, (0.075 + i % 2 * 0.46, 0.55 - i // 2 * 0.35, 0.38, 0.22), POOL_NAMES[pool], "y"
        )
        rows = [row for row in data["rates"] if row["pool_group"] == pool]
        for row in rows:
            x, mid = row["quartile"], row["median"]
            ax.errorbar(
                x,
                mid,
                yerr=[[mid - row["q25"]], [row["q75"] - mid]],
                fmt="o",
                capsize=4,
                markersize=4,
                color=colors[pool],
                linewidth=1.3,
            )
            ax.annotate(
                f"{mid:.2f}%",
                (x, row["q75"]),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                size=8,
            )
        groups = rows[0]["groups"]
        ax.set(xlim=(0.4, groups + 0.6), ylim=(0, upper), ylabel="账号内占比 %")
        ax.set_xticks(
            [row["quartile"] for row in rows],
            [
                f"Q{row['quartile']}\nn={row['people']:,}"
                if groups > 1
                else f"全部\nn={row['people']:,}"
                for row in rows
            ],
        )
    publish(fig, "A05")

    running = 0
    role_total = sum(row["counts"][301] for row in data["gap_bins"][301])
    for row in data["gap_bins"][301]:
        running += row["counts"][301]
        if running >= role_total / 2:
            median_bound = row["hi"]
            break
    fig = page(
        f"角色池半数已闭合五星间隔不超过{median_bound}抽",
        "间隔为池内连续序号之差；各池独立归一\n首段及未闭合尾段排除；缺失历史无法识别",
        6.3,
    )
    scale = max(
        100 * row["counts"][pool] / sum(r["counts"][pool] for r in rows)
        for pool, rows in data["gap_bins"].items()
        for row in rows
    )
    for i, pool in enumerate((200, 301, 302)):
        rows = data["gap_bins"][pool]
        total = sum(row["counts"][pool] for row in rows)
        hbars(
            axis(fig, (0.075, 0.61 - i * 0.245, 0.85, 0.175), f"{POOL_NAMES[pool]}  {total:,}段"),
            [bin_label(row) for row in rows],
            [100 * row["counts"][pool] / total for row in rows],
            [colors[pool]] * len(rows),
            lambda value: f"{value:.1f}%",
            "占本池已闭合间隔的百分比",
            scale,
        )
    publish(fig, "A06")

    items = data["items"]
    total = sum(row["star5"] for row in data["pools"])
    coverage = 100 * sum(row["pulls"] for row in items) / total
    fig = page(
        f"前{len(items)}个原始名称覆盖{coverage:.1f}%五星记录",
        "精确原始名称计数；未合并翻译别名；不等同角色人气",
        5.6,
    )
    hbars(
        axis(fig, (0.075, 0.17, 0.85, 0.62), "五星原始名称记录量"),
        [row["name"] for row in items],
        [row["pulls"] for row in items],
        [theme.MAIN] + [theme.GRAY] * (len(items) - 1),
        lambda value: f"{value:,.0f}",
        "次五星记录",
    )
    publish(fig, "A07")
    return paths
