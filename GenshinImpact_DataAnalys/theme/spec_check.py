# -*- coding: utf-8 -*-
"""
蓝粉 · 规范自检

只盯《图表规范》里的**禁止项**（第 4 节「不用」栏 + 第 5 节），另附两条温和建议。
结论对不对、口径写清没有，靠人审 —— 自动检查只能挡住低级问题。

    import spec_check
    spec_check.lint_figure(fig)     # 触犯禁止项直接抛 SpecViolation
    spec_check.report(fig)          # 只打印，不抛，适合 notebook 末尾随手跑
"""
from __future__ import annotations

import re

from matplotlib.patches import Wedge

# —— 禁止项：触犯即不合规 ——
HARD_RULES = {
    "twin_axis", "3d", "pie", "bar_baseline", "legend_items",
    "tick_size", "commercial_font", "personal_id",
}
# —— 建议：不拦截，只提醒 ——
SOFT_RULES = {"title_len", "source_line"}


class SpecViolation(Exception):
    """图表触犯了《图表规范》的禁止项。"""


# 商业字体名 —— 代码里一个都不许出现
BANNED_FONTS = {
    "microsoft yahei", "微软雅黑", "simhei", "黑体", "simsun", "宋体",
    "pingfang sc", "苹方", "stheiti", "华文黑体", "times new roman",
    "arial", "helvetica", "segoe ui", "calibri", "cambria", "georgia",
}

MIN_TICK_PT = 8.0
MAX_TITLE_CHARS = 40
MAX_LEGEND_ITEMS = 7

# 个人标识：11 位手机号、以及任何 11 位以上的连续数字（IMSI 15 位也在这里面）
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_LONG_DIGITS = re.compile(r"(?<!\d)\d{11,}(?!\d)")


# --------------------------------------------------------------------------- #
# 观测
# --------------------------------------------------------------------------- #


def _twin_count(ax) -> int:
    try:
        return len(ax._twinned_axes.get_siblings(ax))
    except Exception:
        return 1


def _pie_wedges(ax) -> int:
    return sum(1 for p in ax.patches if isinstance(p, Wedge))


def _has_bar(ax) -> bool:
    return any(type(c).__name__ == "BarContainer" for c in ax.containers)


def _fig_texts(fig) -> list[str]:
    out = [t.get_text() for t in fig.texts]
    for ax in fig.axes:
        out += [t.get_text() for t in ax.texts]
        out += [t.get_text() for t in ax.get_xticklabels() + ax.get_yticklabels()]
        lg = ax.get_legend()
        if lg is not None:
            out += [t.get_text() for t in lg.get_texts()]
    return [s for s in out if s]


# --------------------------------------------------------------------------- #
# 检查
# --------------------------------------------------------------------------- #


def check(fig) -> list[tuple[str, str]]:
    """返回 (规则名, 说明) 清单；空列表 = 通过。"""
    bad: list[tuple[str, str]] = []

    # 1 · 双 Y 轴（第 5 节第 1 条）
    for i, ax in enumerate(fig.axes, 1):
        n = _twin_count(ax)
        if n > 1:
            bad.append(("twin_axis",
                        f"双 Y 轴：第 {i} 个坐标区有 {n} 条纵轴。"
                        "两条线的交点全由刻度决定，容易误导 —— "
                        "改成上下两个面板，共用横轴。"))
            break

    # 2 · 3D（第 5 节第 2 条）
    for i, ax in enumerate(fig.axes, 1):
        if getattr(ax, "name", "") == "3d" or hasattr(ax, "get_zlim"):
            bad.append(("3d", f"3D 图：第 {i} 个坐标区。透视让大小失真，改平面图。"))
            break

    # 3 · 饼图 / 环形图（第 4 节「构成」不用栏 + 第 5 节第 3 条）
    for i, ax in enumerate(fig.axes, 1):
        n = _pie_wedges(ax)
        if n:
            bad.append(("pie",
                        f"饼图 / 环形图：第 {i} 个坐标区有 {n} 个扇区。"
                        "人眼比较角度很差 —— 构成改用横向条形 + 百分比标注。"))
            break

    # 4 · 纵轴截断的柱状图（第 5 节第 4 条）
    for i, ax in enumerate(fig.axes, 1):
        if _has_bar(ax) and ax.get_ylim()[0] > 0:
            bad.append(("bar_baseline",
                        f"纵轴截断：第 {i} 个坐标区的柱状图基线在 "
                        f"{ax.get_ylim()[0]:g}，不在 0。柱子的长度就是数值，"
                        "纵轴必须从 0 开始（折线图可以不从 0 开始，但要说明）。"))
            break

    # 5 · 图例超过 7 项（第 5 节第 5 条）
    for i, ax in enumerate(fig.axes, 1):
        lg = ax.get_legend()
        n = len(lg.get_texts()) if lg is not None else 0
        if n > MAX_LEGEND_ITEMS:
            bad.append(("legend_items",
                        f"图例 {n} 项：超过 {MAX_LEGEND_ITEMS} 项。"
                        "改成线尾直接标注，或拆成小多图。"))
            break

    # 6 · 刻度字号小于 8 磅（第 3 节）
    for i, ax in enumerate(fig.axes, 1):
        hit = [lab.get_fontsize()
               for lab in list(ax.get_xticklabels()) + list(ax.get_yticklabels())
               if lab.get_text() and lab.get_fontsize() < MIN_TICK_PT]
        if hit:
            bad.append(("tick_size",
                        f"刻度字号 {min(hit):.1f} 磅：小于 {MIN_TICK_PT:g} 磅。"))
            break

    # 7 · 商业字体名（第 0 节合规红线）—— 只看用户自己声明的，不算 matplotlib 出厂默认
    import matplotlib.pyplot as plt
    from matplotlib import rcParamsDefault
    fam = [str(f).strip() for f in plt.rcParams.get("font.family", [])]
    if fam and [f.lower() for f in fam] != ["sans-serif"]:
        declared = fam
    else:
        stock = list(rcParamsDefault.get("font.sans-serif", []))
        declared = [f for f in plt.rcParams.get("font.sans-serif", []) if f not in stock]
    hit_fonts = [f for f in declared if str(f).strip().lower() in BANNED_FONTS]
    if hit_fonts:
        bad.append(("commercial_font",
                    f"商业字体名：{'、'.join(map(str, hit_fonts))}。"
                    "代码里只能写开源字体，这是一条合规红线。"))

    # 8 · 个人标识（第 5 节第 7 条）
    for s in _fig_texts(fig):
        if _PHONE.search(s) or _LONG_DIGITS.search(s):
            bad.append(("personal_id",
                        f"疑似个人标识：图上出现「{s[:24]}」。"
                        "不出现完整 IMSI 或手机号；个例只显示尾号。"))
            break

    # 9 · 标题长度（第 1 节，建议）
    title = getattr(fig, "_dsh_title", "")
    if title and len(title) > MAX_TITLE_CHARS:
        bad.append(("title_len",
                    f"标题 {len(title)} 字：超过 {MAX_TITLE_CHARS} 字。"
                    "标题写结论，要能一眼读完。"))

    # 10 · 来源行（第 1 节，建议）
    if not getattr(fig, "_dsh_source", None):
        bad.append(("source_line",
                    "缺来源行：左下角建议写「数据来源：…；脚本：…；配置 …」。"))

    return bad


def lint_figure(fig, strict: bool = True) -> list[tuple[str, str]]:
    """检查并打印。strict=True 时，触犯禁止项直接抛 SpecViolation。"""
    bad = check(fig)
    hard = [b for b in bad if b[0] in HARD_RULES]
    soft = [b for b in bad if b[0] not in HARD_RULES]

    if hard:
        print("❌ 触犯规范禁止项：")
        for i, (_, m) in enumerate(hard, 1):
            print(f"  {i}. {m}")
    if soft:
        print("💡 建议：")
        for i, (_, m) in enumerate(soft, 1):
            print(f"  {i}. {m}")
    if not bad:
        print("✅ 图表规范自检通过。")
    if hard and strict:
        raise SpecViolation(f"{len(hard)} 项禁止项不合规，详见上方清单。")
    return bad


def report(fig) -> list[tuple[str, str]]:
    """只报告不抛异常。"""
    return lint_figure(fig, strict=False)
