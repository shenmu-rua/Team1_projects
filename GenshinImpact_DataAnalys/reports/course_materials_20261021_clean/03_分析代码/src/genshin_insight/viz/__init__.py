"""蓝粉主题适配；只有显式调用时才加载 Matplotlib 或修改绘图参数。"""

from __future__ import annotations

import re
from importlib import import_module
from pathlib import Path
from types import ModuleType

from .. import config


def load_theme() -> ModuleType:
    """复用 theme/theme.py，不复制引擎或修改 sys.path。"""
    return import_module("theme.theme")


def apply_theme(width_in: float = 16.0) -> list[str]:
    """显式应用蓝粉主题，并保留可见的标注箭头边线。"""
    if width_in <= 0:
        raise ValueError("画布宽度必须大于 0。")
    engine = load_theme()
    fonts = engine.apply_theme(width_in=width_in)
    # 参考规范明确禁止 patch.linewidth=0，以免标注箭头消失。
    engine.plt.rcParams["patch.linewidth"] = 1.0
    return fonts


def finish(fig, title: str, subtitle: str, source: str, **options) -> float:
    """统一添加标题区；来源必填，默认启用规范要求的主色短条。"""
    if not title.strip() or len(title) > 40:
        raise ValueError("标题必须非空且不超过 40 字。")
    if not source.strip():
        raise ValueError("来源行必须说明数据来源、脚本和配置版本。")
    engine = load_theme()
    accent = options.pop("accent", True)
    bottom = engine.finish(fig, title, subtitle, source, accent=False, **options)
    if accent:
        fig.add_artist(
            engine.Rectangle(
                (options.get("x0", 0.075), 0.978),
                0.38 / fig.get_figwidth(),
                0.055 / fig.get_figheight(),
                transform=fig.transFigure,
                facecolor=engine.MAIN,
                edgecolor="none",
            )
        )
    return bottom


def sequential_cmap():
    """连续数值用主粉由浅到深的单色渐变，遵守图表规范。"""
    engine = load_theme()
    return engine.LinearSegmentedColormap.from_list(
        "genshin_pink", [engine.PINK_100, engine.PINK_300, engine.PINK_500, engine.PINK_700]
    )


def save(fig, path: str | Path, *, ppt: bool = False) -> Path:
    """先检查规范，再以 200 dpi 保存；不会读取数据库。"""
    if not getattr(fig, "_dsh_source", ""):
        raise ValueError("保存前必须通过 viz.finish() 添加来源行。")
    if not re.search(r"\d", getattr(fig, "_dsh_title", "")):
        raise ValueError("图表标题必须包含由聚合计算的数字。")
    width, height = fig.get_size_inches()
    if ppt and abs(width / height - 16 / 9) > 1e-6:
        raise ValueError("本图集画布必须严格为16:9。")
    fig.canvas.draw()
    checker = import_module("theme.spec_check")
    checker.lint_figure(fig, strict=True)
    return load_theme().save(fig, path=path, dpi=config.FIGURE_DPI)
