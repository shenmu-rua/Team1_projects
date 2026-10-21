"""ADS 图集：只接收已保护的聚合，版式和颜色由本地蓝粉主题统一提供。"""

from __future__ import annotations

from textwrap import fill

from ..ads import POOL_NAMES
from . import finish, load_theme, sequential_cmap


def pool_colors():
    theme = load_theme()
    return {100: theme.BRIDGE, 200: theme.PAST, 301: theme.MAIN, 302: theme.BLUE_700}


def page(data, source, title, subtitle, note="", show_period=True):
    theme = load_theme()
    fig = theme.canvas("ppt", width_in=16, height_in=9)
    scope = data["scope"]
    period = (
        f"DS{data['dataset']:02d} · {scope['first_time'][:10]}—{scope['last_time'][:10]}"
        if show_period
        else "各来源的全部留存时间范围"
    )
    finish(fig, title, f"{period}；{subtitle}", source, note=note)
    return fig


def panel(fig, rect, title, grid="x"):
    theme = load_theme()
    ax = theme.axes(fig, rect=rect, grid=grid)
    ax.text(
        0,
        1.045,
        title,
        transform=ax.transAxes,
        fontsize=12.5,
        color=theme.INK,
        weight="bold",
        va="bottom",
    )
    return ax


def bars(ax, labels, values, colors, formatter, unit, label_ratio=0.55, scale=None):
    theme = load_theme()
    peak = scale or max((v for v in values if v is not None), default=1) or 1
    ax.set(xlim=(-peak * label_ratio, peak * 1.4), ylim=(-0.65, len(labels) - 0.35), yticks=[])
    positions = list(reversed(range(len(labels))))
    theme.label_column(ax, list(zip(positions, labels, strict=True)), 0, -peak * 0.035, size=11.5)
    for y, value, color in zip(positions, values, colors, strict=True):
        if value is None:
            ax.text(peak * 0.04, y, "抑制", color=theme.FAINT, va="center", fontsize=12.5)
        else:
            theme.hbar(ax, y, 0, value, min(22, 240 / len(labels)), color)
            theme.value_label(ax, value, y, formatter(value), theme.INK, size=12.5)
    ticks = [0, peak / 2, peak]
    ax.set_xticks(ticks, [f"{v:,.1f}" if peak < 100 else f"{v:,.0f}" for v in ticks])
    ax.set_xlabel(unit, color=theme.MUTED, fontsize=11.5, labelpad=10)


def overview(data, source):
    theme = load_theme()
    rows = sorted(
        (row for row in data["cohorts"] if not row["suppressed"]),
        key=lambda row: row["pulls"],
        reverse=True,
    )
    total = sum(row["pulls"] for row in rows)
    share = 100 * data["scope"]["pulls"] / total
    fig = page(
        data,
        source,
        f"数据集{data['dataset']:02d}占可发布记录的{share:.1f}%",
        "各来源单独汇总；本图左侧为抽数，右侧为账号数",
        "后续图固定使用该数据集；账号数仅在来源内去重，不能相加推算独立人数",
        show_period=False,
    )
    labels = [
        f"数据集{row['dataset_id']:02d}\n{row['first_time'][:7]}—{row['last_time'][:7]}"
        for row in rows
    ]
    colors = [theme.MAIN if row["dataset_id"] == data["dataset"] else theme.PAST for row in rows]
    for x, key, heading, unit in [
        (0.075, "pulls", "记录规模", "万抽"),
        (0.525, "people", "账号规模", "个账号"),
    ]:
        factor = 10000 if key == "pulls" else 1
        bars(
            panel(fig, (x, 0.22, 0.4, 0.55), heading),
            labels,
            [row[key] / factor for row in rows],
            colors,
            (lambda v: f"{v:,.1f}") if factor > 1 else (lambda v: f"{v:,.0f}"),
            unit,
        )
    return fig


def pools(data, source):
    rows = sorted(data["pools"], key=lambda row: row["pulls"] or 0, reverse=True)
    peak = rows[0]
    share = 100 * peak["pulls"] / data["scope"]["pulls"]
    fig = page(
        data,
        source,
        f"{POOL_NAMES[peak['pool_group']]}贡献{share:.1f}%的记录",
        "301/400合并为角色活动池；左右面板使用独立坐标轴",
        "五星占比＝记录内五星数÷抽数；受样本选择与记录完整性影响，不代表官方概率",
    )
    labels = [POOL_NAMES[row["pool_group"]] for row in rows]
    colors = [pool_colors()[row["pool_group"]] for row in rows]
    bars(
        panel(fig, (0.075, 0.22, 0.4, 0.55), "各卡池抽数"),
        labels,
        [row["pulls"] / 10000 if row["pulls"] is not None else None for row in rows],
        colors,
        lambda v: f"{v:,.1f}",
        "万抽",
        0.72,
    )
    rates = [
        100 * row["star5"] / row["pulls"] if row["star5"] is not None else None for row in rows
    ]
    bars(
        panel(fig, (0.525, 0.22, 0.4, 0.55), "记录内五星占比"),
        labels,
        rates,
        colors,
        lambda v: f"{v:.2f}%",
        "% 的抽数",
        0.72,
    )
    return fig


def months(data, source):
    import numpy as np
    import pandas as pd

    rows = [row for row in data["months"] if row["pulls"] is not None]
    peak = max(rows, key=lambda row: row["pulls"])
    fig = page(
        data,
        source,
        f"{peak['month']}单池月记录达{peak['pulls'] / 10000:,.1f}万抽",
        "按记录时间自然月汇总；四个面板的纵轴尺度各自独立",
        "起止月可能不完整；空缺不插值；时区未知；波动反映留存记录，不能解释为活跃或版本效应",
    )
    dates = pd.date_range(
        data["scope"]["first_time"][:7], data["scope"]["last_time"][:7], freq="MS"
    )
    for i, pool in enumerate(POOL_NAMES):
        ax = panel(
            fig, (0.075 + i % 2 * 0.45, 0.51 - i // 2 * 0.34, 0.4, 0.24), POOL_NAMES[pool], "y"
        )
        lookup = {row["month"]: row["pulls"] for row in data["months"] if row["pool_group"] == pool}
        values = [lookup.get(date.strftime("%Y-%m")) for date in dates]
        y = np.array([v / 10000 if v is not None else np.nan for v in values])
        ax.plot(dates, y, color=pool_colors()[pool], linewidth=2.5, marker=".", markersize=4)
        ax.set(ylim=(0, max(1, np.nanmax(y) * 1.3)), ylabel="万抽")
        indexes = sorted(set([0, len(dates) // 3, len(dates) * 2 // 3, len(dates) - 1]))
        ax.set_xticks(dates[indexes], [dates[index].strftime("%y-%m") for index in indexes])
        if np.isfinite(y).any():
            j = int(np.nanargmax(y))
            ax.annotate(
                f"{y[j]:,.1f}",
                (dates[j], y[j]),
                xytext=(0, 7),
                textcoords="offset points",
                ha="center",
                color=pool_colors()[pool],
                fontsize=12.5,
            )
    return fig


def clock(data, source):
    import numpy as np
    from matplotlib.colors import LogNorm, Normalize

    theme = load_theme()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    released = [row for row in data["clock"] if row["pulls"] is not None]
    peak = max(released, key=lambda row: row["pulls"])
    fig = page(
        data,
        source,
        f"{weekdays[peak['weekday']]}{peak['hour']}时记录最多，计{peak['pulls'] / 10000:.1f}万抽",
        "星期×小时累计抽数；每格为万抽；按库中无时区时间直接解析",
        "统计的是留存抽卡时间，不是在线时长或活跃人数；没有曝光天数校正",
    )
    matrix = np.full((7, 24), np.nan)
    for row in released:
        matrix[row["weekday"], row["hour"]] = row["pulls"] / 10000
    low, high = float(np.nanmin(matrix)), float(np.nanmax(matrix))
    norm = LogNorm(low, high) if low > 0 and high / low >= 100 else Normalize(0, high)
    scale = "对数色阶" if isinstance(norm, LogNorm) else "线性色阶"
    ax = panel(fig, (0.075, 0.23, 0.79, 0.54), f"每格：累计万抽 · {scale}", None)
    cmap = sequential_cmap()
    cmap.set_bad(theme.GRAY)
    mesh = ax.imshow(matrix, aspect="auto", extent=(0, 24, 6.5, -0.5), cmap=cmap, norm=norm)
    ax.set(xlim=(-1.8, 24), ylim=(6.5, -0.5), yticks=[], xlabel="记录中的小时（时区未知）")
    ax.set_xticks([h + 0.5 for h in range(24)], [f"{h:02}" for h in range(24)])
    theme.label_column(ax, list(enumerate(weekdays)), 0, -0.25, size=11.5)
    for day in range(7):
        for hour in range(24):
            value = matrix[day, hour]
            label = (
                "抑制"
                if not np.isfinite(value)
                else (f"{value:.2f}" if value < 0.1 else f"{value:.1f}")
            )
            ax.text(
                hour + 0.5,
                day,
                label,
                ha="center",
                va="center",
                fontsize=11.5,
                color=theme.BG if np.isfinite(value) and norm(value) > 0.65 else theme.INK,
            )
    color_ax = theme.axes(fig, rect=(0.89, 0.23, 0.016, 0.54), grid=None)
    colorbar = fig.colorbar(mesh, cax=color_ax)
    ticks = np.geomspace(low, high, 5) if isinstance(norm, LogNorm) else np.linspace(0, high, 5)
    colorbar.set_ticks(ticks, labels=[f"{v:,.2f}" for v in ticks])
    colorbar.ax.tick_params(labelsize=11.5, length=0)
    return fig


def bin_label(row):
    return f"{row['lo']:,}+" if row["hi"] is None else f"{row['lo']:,}–{row['hi']:,}"


def volumes(data, source):
    import numpy as np

    theme = load_theme()
    rows = data["volume_bins"]
    counts = [row["counts"][0] for row in rows]
    total = sum(counts)
    labels = [bin_label(row) for row in rows]
    fig = page(
        data,
        source,
        f"每个账号的留存抽数中位数为{data['volume_median']:,.0f}抽",
        "来源内按账号合并所有卡池；左侧分箱分布，右侧分箱累计分布",
        "仅描述已留存记录量；不能推算总投入、付费或完整游戏历史；稀疏尾部合并相邻箱",
    )
    bars(
        panel(fig, (0.075, 0.24, 0.4, 0.53), "账号记录量分布"),
        labels,
        [100 * count / total for count in counts],
        [theme.MAIN] * len(rows),
        lambda v: f"{v:.1f}%",
        "% 的账号",
        0.72,
    )
    ax = panel(fig, (0.55, 0.24, 0.375, 0.53), "在各箱上界内累计的账号占比", "y")
    cdf = 100 * np.cumsum(counts) / total
    ax.plot(range(len(rows)), cdf, marker="o", color=theme.MAIN, linewidth=2.5)
    ax.axhline(50, color=theme.AXIS, linestyle="--", linewidth=1)
    for i, value in enumerate(cdf):
        ax.annotate(
            f"{value:.1f}%",
            (i, value),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            fontsize=12.5,
            color=theme.INK,
        )
    ax.set_xticks(
        range(len(rows)), [f"≤{row['hi']:,}" if row["hi"] else "全部" for row in rows], rotation=25
    )
    ax.set(ylim=(0, 113), ylabel="累计账号占比（%）", xlabel="抽数分箱上界；末端开放箱记作全部")
    return fig


def rates(data, source):
    role = [row for row in data["rates"] if row["pool_group"] == 301]
    last = max(role, key=lambda row: row["quartile"])
    fig = page(
        data,
        source,
        f"角色池高记录量组的五星占比中位数为{last['median']:.2f}%",
        "各池按账号抽数分组，重复边界合并；点为中位数，线为25%—75%分位区间",
        "每账号等权、无个人散点；区间不是置信区间；记录量并非付费，分组差异不表示因果",
    )
    upper = max(row["q75"] for row in data["rates"]) * 1.35
    for i, pool in enumerate(POOL_NAMES):
        ax = panel(
            fig, (0.075 + i % 2 * 0.45, 0.51 - i // 2 * 0.34, 0.4, 0.24), POOL_NAMES[pool], "y"
        )
        rows = [row for row in data["rates"] if row["pool_group"] == pool]
        for row in rows:
            x, mid = row["quartile"], row["median"]
            ax.errorbar(
                x,
                mid,
                yerr=[[mid - row["q25"]], [row["q75"] - mid]],
                fmt="o",
                capsize=8,
                color=pool_colors()[pool],
                linewidth=2.5,
                markersize=7,
            )
            ax.annotate(
                f"{mid:.2f}% · n={row['people']:,}",
                (x, row["q75"]),
                xytext=(0, 6),
                textcoords="offset points",
                ha="center",
                fontsize=10.5,
                color=load_theme().INK,
            )
        if not rows:
            ax.text(
                0.5,
                0.5,
                "记录量取值不足以分四组",
                transform=ax.transAxes,
                ha="center",
                color=load_theme().MUTED,
            )
        groups = rows[0]["groups"] if rows else 4
        ax.set(xlim=(0.4, groups + 0.6), ylim=(0, max(upper, 1)), ylabel="每账号五星占比（%）")
        labels = (
            ["Q1 低", "Q2", "Q3", "Q4 高"]
            if groups == 4
            else [f"组{j}/{groups}" for j in range(1, groups + 1)]
            if groups > 1
            else ["全部账号（分组退化）"]
        )
        ax.set_xticks(range(1, groups + 1), labels)
    return fig


def gaps(data, source):
    bins, colors = data["gap_bins"], pool_colors()
    if not all(bins.values()):
        raise ValueError("五星间隔分箱未达到发布门槛。")
    rows = bins[301]
    total = sum(row["counts"][301] for row in rows)
    running = 0
    bound = None
    for row in rows:
        running += row["counts"][301]
        if running >= total / 2:
            bound = row["hi"]
            break
    title = (
        f"角色池半数记录内五星间隔不超过{bound}抽"
        if bound
        else f"角色池可分析{total:,}段记录内五星间隔"
    )
    quality = data["gap_quality"]
    coverage = 100 * quality["eligible_player_pools"] / quality["player_pools"]
    fig = page(
        data,
        source,
        title,
        "相邻已记录五星的序号差（抽）；各池独立归一、分别合并稀疏尾箱",
        f"排序明确的账号池组合占{coverage:.1f}%；首段和未闭合尾段排除；缺失历史无法识别，不代表真实保底",
    )
    scale = max(
        100 * row["counts"][pool] / sum(r["counts"][pool] for r in bins[pool])
        for pool in bins
        for row in bins[pool]
    )
    for i, pool in enumerate((200, 301, 302)):
        rows = bins[pool]
        labels = [bin_label(row) for row in rows]
        counts = [row["counts"][pool] for row in rows]
        total = sum(counts)
        ax = panel(fig, (0.075 + i * 0.292, 0.22, 0.266, 0.55), f"{POOL_NAMES[pool]} · {total:,}段")
        bars(
            ax,
            labels,
            [100 * n / total for n in counts],
            [colors[pool]] * len(rows),
            lambda v: f"{v:.1f}%",
            "% 的已闭合区间",
            0.7,
            scale=scale,
        )
    return fig


def items(data, source):
    theme = load_theme()
    rows = data["items"]
    released_total = sum(row["star5"] for row in data["pools"] if row["star5"] is not None)
    share = 100 * sum(row["pulls"] for row in rows) / released_total
    fig = page(
        data,
        source,
        f"前{len(rows)}个五星原始名称覆盖{share:.1f}%的五星记录",
        "按库中原始名称汇总后排序；角色与武器均可进入榜单",
        "多语言名称未合并，不能直接解释为角色人气；仅展示贡献账号数下界≥5的名称，不使用待复核类型编码",
    )
    labels = [fill(" ".join(row["name"].split()), width=23) for row in rows]
    ax = panel(fig, (0.075, 0.17, 0.85, 0.60), "五星记录量（原始名称）")
    bars(
        ax,
        labels,
        [row["pulls"] for row in rows],
        [theme.MAIN] + [theme.GRAY] * (len(rows) - 1),
        lambda v: f"{v:,.0f}次",
        "次五星记录",
        0.65,
    )
    return fig


PLOTS = (
    ("Q01_数据集范围", overview),
    ("A01_卡池构成与五星占比", pools),
    ("A02_卡池月度记录", months),
    ("A03_星期小时热力矩阵", clock),
    ("A04_账号留存记录量分布", volumes),
    ("A05_账号记录量分组五星占比", rates),
    ("A06_记录内五星间隔分布", gaps),
    ("A07_五星原始名称记录榜", items),
)
