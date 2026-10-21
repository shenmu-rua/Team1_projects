# -*- coding: utf-8 -*-
"""
蓝粉 · 图表主题引擎

冷场暖图：蓝做「场」（地面、结构、过去），粉做「图」（现在、重点、增长），
雾紫卡在两者中间做过渡 —— 蓝和粉在色轮上隔得远，中间那层紫是关键。

尺寸约定：所有字号以原主题画布 **16 in** 为基准，画布变宽变窄时按比例缩放，
保证任何尺寸下版面比例与原主题一致（标题 22 pt、副标题 12 pt、刻度 11.5 pt…）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib import font_manager
from matplotlib import pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path as MplPath

# --------------------------------------------------------------------------- #
# 一、配色
# --------------------------------------------------------------------------- #

# 冷轴 · 烟蓝 —— 场 / 过去 / 对比
BLUE_700 = "#30496C"
BLUE_600 = "#42608C"
BLUE_500 = "#5A7BAC"          # 主蓝
BLUE_400 = "#7D9DC8"
BLUE_300 = "#A6C0DE"
BLUE_200 = "#CBDCEF"
BLUE_100 = "#E6EEF8"

# 暖轴 · 藕粉 —— 图 / 现在 / 重点
PINK_700 = "#803A55"
PINK_600 = "#A64D6E"
PINK_500 = "#C9668B"          # 主粉
PINK_400 = "#DD86A5"
PINK_300 = "#EBABC2"
PINK_200 = "#F5CCDB"
PINK_100 = "#FBE7EE"

# 桥 · 雾紫
VIOLET_500 = "#7F71B4"
VIOLET_400 = "#9E92CC"        # 桥色
VIOLET_300 = "#BDB4E0"
VIOLET_200 = "#D8D3EE"

# 画布
BG = "#F6F8FC"                # 页边：极淡冷白，带蓝调
PANEL = "#EEF4FB"             # 地面：雾蓝（蓝 = 场）
GRID = "#DCE7F4"              # 网格：淡蓝
RIBBON = "#E5E2F2"            # 连接带兜底色（渐变不可用时）
AXIS = "#C3D0E0"              # 坐标轴：已淡化
SURFACE = "#FFFFFF"

# 文字 —— 蓝紫调灰阶
INK = "#1A2233"               # 主文字
INK_SOFT = "#3B4761"          # 刻度 / 类目名 / 轴标题
MUTED = "#68758F"             # 次级说明
FAINT = "#8B97AE"             # 来源行

# 文字别名（与原主题 API 一致）
TEXT = INK
TEXT_SUB = INK_SOFT
TEXT_MUTED = MUTED
TEXT_FAINT = FAINT

# 语义 —— 刻意跳出蓝粉两轴，好坏一眼可辨
RED = "#B2574A"
AMBER = "#C28A3A"
GREEN = "#4E8C7E"

# 语义别名（与「黄红」保持同一套 API）
ALERT = RED                   # 下降 / 不通过
WARN = AMBER                  # 警告
OK = GREEN                    # 通过

# 语义别名
MAIN = PINK_500               # 主色 = 要读者看的那个
MAIN_LIGHT = PINK_200
MAIN_MID = PINK_400
PAST = BLUE_500               # 过去 / 基线
NOW = PINK_500                # 现在 / 现状
BRIDGE = VIOLET_400           # 双色同现时的第三色
GRAY = "#C4CAD3"              # 背景对象（不强调的类别）

# 多系列顺序取色：冷暖交替，第三位起用桥色
SERIES = [PINK_500, BLUE_500, VIOLET_400, PINK_300, BLUE_300, MUTED]
# 连续色板：低（冷·静）→ 高（暖·忙），途经雾紫
SEQ = ["#F2F6FC", "#DCE7F4", "#C3D6EC", "#B9B8DF", "#C3A2CE",
       "#D486A8", "#C9668B", "#A64D6E", "#803A55"]
# 双轴渐变端点
AXIS_RAMP = [BLUE_500, VIOLET_400, PINK_500]

# --------------------------------------------------------------------------- #
# 二、字体：只写开源字体，一个商业字体名都不出现
# --------------------------------------------------------------------------- #

OPEN_FONTS = [
    "Noto Sans SC",            # 本主题指定字体
    "Source Han Sans SC",      # 同一套字形的另一个发行名
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",        # 泛 CJK 合集，应急
    "DejaVu Sans",             # 兜底：补负号与上下标
]

FONT_DIRS = [
    Path(__file__).resolve().parent / "fonts",           # 与 theme.py 同级（推荐）
    Path(__file__).resolve().parent.parent / "fonts",    # 上一级（分享包解压后的原样结构）
]


def register_fonts() -> list[str]:
    """加载主题目录内的字体（若有），返回文件名列表。"""
    loaded: list[str] = []
    for d in FONT_DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.ttf")) + sorted(d.glob("*.otf")):
            try:
                font_manager.fontManager.addfont(str(p))
                loaded.append(p.name)
            except Exception:
                continue
    return loaded


def available_fonts() -> list[str]:
    """本机实际生效的开源中文字体，按优先级返回。"""
    have = {f.name for f in font_manager.fontManager.ttflist}
    return [n for n in OPEN_FONTS[:-1] if n in have]


# --------------------------------------------------------------------------- #
# 三、主题装载
# --------------------------------------------------------------------------- #

REF_WIDTH_IN = 16.0          # 字号基准宽度 —— 与原主题画布一致
_scale = 1.0


def apply_theme(width_in: float = REF_WIDTH_IN) -> dict:
    """
    装载主题。返回本机生效的开源中文字体列表；一个都没有时会告警。

    width_in：本次出图的画布宽度，用于按比例缩放字号。换画布尺寸就重调一次。
    """
    global _scale
    _scale = width_in / REF_WIDTH_IN
    register_fonts()

    # 回退链里没装的字体会让 matplotlib 逐个刷 findfont 警告，压掉；
    # 实际生效的字体由本函数的返回值和下面的告警负责说明。
    import logging
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

    if not available_fonts():
        print("⚠️ 本机没有课程用的开源中文字体，中文会变方框。"
              "装 Source Han Sans SC 或 Noto Sans SC 后重启内核。")
        print("   不要改用系统自带的中文商业字体顶替。")

    # 逐字回退必须写进 font.family（只写 font.sans-serif 时只用第一个找到的字体，
    # 缺的负号、上下标不会由 DejaVu Sans 补上）
    plt.rcParams.update({
        "font.family": OPEN_FONTS,
        "axes.unicode_minus": True,
        "figure.facecolor": BG,
        "figure.edgecolor": BG,
        "savefig.facecolor": BG,
        "savefig.edgecolor": BG,
        "axes.facecolor": PANEL,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.labelcolor": MUTED,
        "axes.grid": False,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.prop_cycle": plt.cycler(color=SERIES),
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "legend.frameon": False,
        "lines.linewidth": 1.8,
        "lines.solid_capstyle": "round",
        "lines.dash_capstyle": "round",
        "patch.linewidth": 0,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "text.antialiased": True,
    })
    return available_fonts()


def pt(x: float) -> float:
    """把基准字号换算成当前画布下的字号。"""
    return x * _scale


# --------------------------------------------------------------------------- #
# 四、画布与坐标轴
# --------------------------------------------------------------------------- #

PRESETS = {
    "slide": (16.0, 9.4),        # 与原主题画布完全一致（默认）
    "ppt": (13.333, 7.5),        # 严格 16:9
    "report": (6.06, 3.56),      # 报告插图宽 15.4 cm（字号同比缩小）
}


def canvas(kind: str = "slide", width_in: float | None = None,
           height_in: float | None = None, dpi: int = 200):
    """建画布。默认 16:9、200 dpi（规范第 8 节）。"""
    if width_in is None or height_in is None:
        w, h = PRESETS.get(kind, PRESETS["slide"])
        width_in = width_in or w
        height_in = height_in or h
    fig = plt.figure(figsize=(width_in, height_in), dpi=dpi, facecolor=BG)
    fig._dsh_scale = width_in / REF_WIDTH_IN
    return fig


def axes(fig, top: float | None = None, bottom: float = 0.135,
         left: float = 0.075, right: float = 0.925, rect=None,
         grid: str | None = "y", frame: str = "faded",
         x_axis: bool = True, y_axis: bool = True):
    """
    画坐标区。默认带一圈**淡色闭合框**。

    frame：
        "faded"  闭合框，用与坐标轴同档的淡色（默认）—— 版面有骨架，但没有任何一处是重的
        "none"   完全不画框，只留坐标轴
        "ink"    闭合墨黑框，最重，适合打印或需要强边界时

    为什么默认不是无框：地面（PANEL）只比页边深一丁点，去掉框之后整块版面会糊在一起，
    左边的标签栏分隔线也失去附着点。淡框是"有结构"和"不压数据"之间的折中。

    坐标轴用 AXIS 淡色、1.0 pt，不打刻度线。top 传 finish() 的返回值，两者就不会打架。
    """
    if rect is None:
        rect = (left, bottom, right - left, (top if top is not None else 0.80) - bottom)
    ax = fig.add_axes(rect)
    ax.set_facecolor(PANEL)
    closed = frame in ("faded", "ink")
    for s in ("top", "right"):
        ax.spines[s].set_visible(closed)
    ax.spines["bottom"].set_visible(closed or x_axis)
    ax.spines["left"].set_visible(closed or y_axis)
    edge = INK if frame == "ink" else AXIS
    for s in ("top", "right", "bottom", "left"):
        ax.spines[s].set_color(edge)
        ax.spines[s].set_linewidth(1.0)
    if grid:
        ax.grid(True, axis=grid, color=GRID, lw=1.1, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", length=0, colors=INK_SOFT,
                   labelsize=max(pt(11.5), 8.0))   # 刻度不得小于 8 磅
    return ax


def label_column(ax, rows, x_sep: float, x_text: float, size: float | None = None,
                 color: str | None = None, weight=None, ha: str = "right"):
    """
    框内左侧标签栏：类目名写在坐标区里面，配一条贯通上下的 y 轴淡线。

    这样坐标区左边界可以留在版心（0.075）上，与标题、来源行对齐，
    类目名也不会被画面左边缘切掉。

        ax = T.axes(fig, top=top)          # 左边界 0.075
        ax.set_xlim(-52, 620)              # 左边留出标签栏的宽度
        T.label_column(ax, [(4, "南巷奶咖"), (3, "果C工坊")], x_sep=0, x_text=-6)
    """
    ax.axvline(x_sep, color=AXIS, lw=1.0, zorder=1)
    for y, text in rows:
        ax.text(x_text, y, text, fontsize=size or pt(12.5),
                fontweight=weight or "medium", color=color or INK_SOFT,
                ha=ha, va="center", zorder=6)


# --------------------------------------------------------------------------- #
# 五、标题块 / 来源行 / 水印（规范的「五部分」）
# --------------------------------------------------------------------------- #


def finish(fig, title: str, subtitle: str = "", source: str = "", *,
           note: str = "", filename: str | None = None, legend: list | None = None,
           x0: float = 0.075, top: float = 0.955, gap: float = 0.016,
           accent: bool = False) -> float:
    """
    补上标题、副标题、限制、图例、来源行。

    标题     写结论、含关键数字、不超过 40 字（数字请用 f-string 算出来）
    副标题   口径：对象、时间、统计方法、限制
    来源行   数据来源、脚本或程序、配置版本

    accent=True 才在标题左侧加那条主色短条（规范 v1.3 的部件）。
    默认**不画** —— 它不承载任何信息，读者只会看到一条"意义不明的红杠"。

    **返回标题块底部的 figure 坐标 y**，交给 axes(fig, top=…)，两者就不会打架：

        top = T.finish(fig, 标题, 副标题, 来源, legend=[…])
        ax  = T.axes(fig, top=top, grid="x")
    """
    def dy(points: float, lead: float = 1.5) -> float:
        return points * lead / (fig.get_figheight() * 72)

    fig._dsh_title = title          # 供 spec_check 自检
    fig._dsh_source = source

    if accent:
        bar_w = 0.38 / fig.get_figwidth()
        bar_h = 0.055 / fig.get_figheight()
        fig.add_artist(Rectangle((x0, top - dy(pt(22), 0.66) - bar_h / 2), bar_w, bar_h,
                                 transform=fig.transFigure, facecolor=MAIN,
                                 edgecolor="none"))
        tx = x0 + bar_w + 0.013
    else:
        tx = x0

    fig.text(tx, top, title, fontsize=pt(22), fontweight="bold",
             color=INK, va="top", ha="left")

    y = top - dy(pt(22), 1.42)
    if subtitle:
        fig.text(x0, y, subtitle, fontsize=pt(12), color=MUTED, va="top", ha="left")
        y -= dy(pt(12), 1.62)
    if note:
        fig.text(x0, y, note, fontsize=pt(12), color=FAINT, va="top", ha="left")
        y -= dy(pt(12), 1.62)
    if legend:
        y -= dy(pt(12), 0.30)
        draw_legend(fig, legend, y - dy(pt(12), 0.55), x0=x0)
        y -= dy(pt(12), 1.30)

    if source:
        fig.text(x0, 0.028, source, fontsize=pt(9.5), color=FAINT,
                 va="bottom", ha="left")
    if filename:
        fig._dsh_filename = filename
    return y - gap


def draw_legend(fig, items: list, y: float, x0: float = 0.075, gap: float = 0.026):
    """
    横排图例。最多 7 项；再多了改用线尾直接标注。

    每种色块各自算「半宽」，文字从色块右缘再加一点空隙开始 ——
    否则线形色块（±0.013）会和文字起点（+0.012）叠在一起。
    """
    if len(items) > 7:
        raise ValueError("图例超过 7 项：改成线尾直接标注，或拆成小多图。")
    r = fig.canvas.get_renderer()
    w_in = fig.get_figwidth()
    pad = 0.007                      # 色块与文字之间的空隙（figure 比例）

    x = x0
    for it in items:
        kind, color = it.get("kind", "fill"), it.get("color", MAIN)
        if kind == "hollow":
            half = (pt(12) / 2 + pt(2.2) / 2) / 72 / w_in
            fig.add_artist(Line2D([x], [y], transform=fig.transFigure, linestyle="none",
                                  marker="o", markersize=pt(12), markerfacecolor=SURFACE,
                                  markeredgecolor=color, markeredgewidth=pt(2.2)))
        elif kind == "fill":
            half = (pt(12) / 2 + pt(2.2) / 2) / 72 / w_in
            fig.add_artist(Line2D([x], [y], transform=fig.transFigure, linestyle="none",
                                  marker="o", markersize=pt(12), markerfacecolor=color,
                                  markeredgecolor=SURFACE, markeredgewidth=pt(2.2)))
        elif kind == "line":
            half = 0.013
            fig.add_artist(Line2D([x - half, x + half], [y, y], transform=fig.transFigure,
                                  color=color, lw=pt(3.4), solid_capstyle="butt"))
        elif kind == "square":
            half = 0.006
            fig.add_artist(Rectangle((x - half, y - half), half * 2, half * 2,
                                     transform=fig.transFigure, facecolor=color,
                                     edgecolor="none"))
        else:
            half = 0.006

        tx = x + half + pad
        t = fig.text(tx, y, it["label"], fontsize=pt(12), fontweight="medium",
                     color=MUTED, va="center", ha="left")
        x = tx + t.get_window_extent(renderer=r).width / fig.bbox.width + gap
    return x


def watermark(target, text: str = "模拟数据", color: str | None = None,
              alpha: float = 0.085, size: float | None = None,
              rotation: float = 30, x: float = 0.54, y: float = 0.46):
    """
    模拟分区出的图必须打水印（规范第 7 节）。

    target 传 Axes（推荐，水印只盖绘图区，不压标题）或 Figure。
    """
    kw = dict(fontsize=size or pt(76), fontweight="bold",
              color=color or VIOLET_400, alpha=alpha, rotation=rotation,
              ha="center", va="center", zorder=0)
    if hasattr(target, "transAxes"):                 # Axes
        target.text(x, y, text, transform=target.transAxes, **kw)
    else:                                            # Figure
        target.text(0.5, 0.5, text, **kw)


def source_line(data: str, script: str = "", config: str = "") -> str:
    """按规范拼来源行：数据来源、脚本或程序、配置版本。"""
    parts = [f"数据来源：{data}"] if data else []
    if script:
        parts.append(f"脚本：{script}")
    if config:
        parts.append(f"配置 {config}")
    return "；".join(parts)


def save(fig, path=None, dpi: int | None = None):
    """保存。默认 200 dpi（规范第 8 节）。"""
    if path is None:
        path = getattr(fig, "_dsh_filename", None) or "figure.png"
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=dpi or 200, facecolor=fig.get_facecolor())
    plt.close(fig)
    return p


# --------------------------------------------------------------------------- #
# 六、图元
# --------------------------------------------------------------------------- #


def _pt_x(ax, points: float) -> float:
    px = points * ax.figure.dpi / 72.0
    inv = ax.transData.inverted()
    a, _ = inv.transform((0.0, 0.0))
    b, _ = inv.transform((px, 0.0))
    return abs(b - a)


def gradient_hbar(ax, x0, x1, y, c0: str, c1: str, lw: float, zorder: int = 3,
                  n: int = 140, cmap=None):
    """横向渐变条 —— 从「过去色」平顺走到「现在色」；给 cmap 可走多段（如经桥色）。"""
    xs = np.linspace(x0, x1, n + 1)
    ys = np.full(n, float(y))
    segs = np.stack([np.stack([xs[:-1], ys], axis=1),
                     np.stack([xs[1:], ys], axis=1)], axis=1)
    cmap = cmap or LinearSegmentedColormap.from_list("_g", [c0, c1])
    lc = LineCollection(segs, colors=[cmap(i / (n - 1)) for i in range(n)],
                        linewidths=lw, capstyle="butt", zorder=zorder)
    ax.add_collection(lc)
    return lc


def hbar(ax, y, x0, x1, height_pt: float, color: str, zorder: int = 3):
    """直角横条。"""
    return ax.hlines(y, x0, x1, linewidth=height_pt, color=color, zorder=zorder,
                     capstyle="butt")


def dumbbell(ax, y, before, after, decline: bool = False, zorder: int = 3,
             ribbon_pt: float = 9.0, center: bool = True):
    """
    前后对比哑铃：连接带做「过去色 → 现在色」渐变。
    过去 = 蓝空心点，现在 = 粉实心点；下降换赤陶。
    """
    c_after = RED if decline else PINK_500
    cmap = (LinearSegmentedColormap.from_list("_dec", [PAST, RED])
            if decline else axis_cmap())
    gradient_hbar(ax, before, after, y, PAST, c_after, pt(ribbon_pt),
                  zorder=zorder, cmap=cmap)
    if center:
        ax.plot([before, after], [y, y], color=INK, lw=pt(1.0), alpha=0.45,
                solid_capstyle="butt", zorder=zorder + 1)
    ax.plot([before], [y], marker="o", markersize=pt(12), linestyle="none",
            markerfacecolor=SURFACE, markeredgecolor=PAST, markeredgewidth=pt(2.0),
            zorder=zorder + 2)
    ax.plot([after], [y], marker="o", markersize=pt(14), linestyle="none",
            markerfacecolor=c_after, markeredgecolor="none", zorder=zorder + 3)
    return c_after


def value_label(ax, x, y, text: str, color: str, dx_pt: float = 4, ha: str = "left",
                size: float | None = None, va: str = "center", weight=None, zorder: int = 6):
    """数值标签。字号 13 pt（随画布缩放）。"""
    off = _pt_x(ax, dx_pt) * (1 if ha == "left" else -1)
    return ax.text(x + off, y, text, color=color, fontsize=size or pt(13),
                   fontweight=weight or "medium", ha=ha, va=va, zorder=zorder)


def gradient_fill_between(ax, x, y, base: float, color: str,
                          alpha_top: float = 0.22, alpha_bottom: float = 0.0, zorder: int = 2):
    """线下渐变面积。"""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    b = np.full_like(y, base, float)
    verts = list(zip(x, y)) + list(zip(x[::-1], b[::-1])) + [(x[0], base)]
    codes = [MplPath.MOVETO] + [MplPath.LINETO] * (2 * len(x) - 1) + [MplPath.CLOSEPOLY]
    clip = PathPatch(MplPath(verts, codes), facecolor="none", edgecolor="none")
    ax.add_patch(clip)
    rgb = to_rgb(color)
    n = 256
    img = np.empty((n, 1, 4))
    img[:, :, 0], img[:, :, 1], img[:, :, 2] = rgb
    img[:, :, 3] = np.linspace(alpha_top, alpha_bottom, n).reshape(-1, 1)
    top = float(np.nanmax(y)) if np.nanmax(y) > base else base + 1.0
    im = ax.imshow(img, extent=[x.min(), x.max(), base, top], origin="upper",
                   aspect="auto", zorder=zorder, interpolation="bilinear")
    im.set_clip_path(clip)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    return im


def seq_cmap(name: str = "bluepink") -> LinearSegmentedColormap:
    """连续色板：低=冷（蓝），高=暖（粉）。不用彩虹色阶。"""
    return LinearSegmentedColormap.from_list(name, SEQ)


def axis_cmap(name: str = "bluepink-axis") -> LinearSegmentedColormap:
    """双轴渐变：蓝 ↔ 雾紫 ↔ 粉。桥色就藏在这条渐变里。"""
    return LinearSegmentedColormap.from_list(name, AXIS_RAMP)


def ramp(n: int, c0: str, c1: str) -> list:
    cmap = LinearSegmentedColormap.from_list("_r", [c0, c1])
    return [cmap(i / max(n - 1, 1)) for i in range(n)]


def bar_baseline_zero(ax, values) -> bool:
    """柱状图纵轴必须从 0 开始（规范第 5 节第 4 条）。返回是否合规。"""
    lo = min(0, float(np.min(values)))
    ax.set_ylim(bottom=lo)
    return lo == 0
