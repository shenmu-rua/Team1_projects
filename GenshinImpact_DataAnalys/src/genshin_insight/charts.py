"""完整图集调度；显式运行后才读清洗库、加载绘图库和创建产物。"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

from . import config
from .ads import MIN_PEOPLE, collect


def generate(database: Path | None = None, output: Path | None = None, dataset: int = 3) -> Path:
    """输出八张PNG、受保护ADS、复现清单和Markdown报告；不覆盖旧产物。"""
    database = (
        Path(database)
        if database
        else max(
            config.DATA_DIR.glob("genshin_clean_*.db"),
            key=lambda path: path.stat().st_mtime_ns,
            default=None,
        )
    )
    if database is None:
        raise FileNotFoundError("未找到清洗结果，请先运行 clean。")
    database = database.resolve(strict=True)
    if not database.is_relative_to(config.PROJECT_ROOT.resolve()):
        raise ValueError("只允许读取本项目内部的清洗库。")
    output = (
        output or config.IMAGE_DIR / f"analysis_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    ).resolve()
    if not output.is_relative_to(config.PROJECT_ROOT.resolve()):
        raise ValueError("图表与汇总产物必须保存在本项目内部。")
    output.mkdir(parents=True, exist_ok=False)

    def progress(stage):
        print(json.dumps({"stage": stage}, ensure_ascii=False), flush=True)

    data = collect(database, dataset, progress)
    (output / "ads.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    import matplotlib

    matplotlib.use("Agg")
    from . import viz
    from .viz.plots import PLOTS

    fonts = viz.apply_theme(16)
    if not any("Noto" in name or "Source Han" in name for name in fonts):
        raise RuntimeError("缺少主题要求的开源中文字体，停止生成。")
    settings = {
        "version": config.CHART_CONFIG_VERSION,
        "dataset": dataset,
        "minimum_people": MIN_PEOPLE,
        "dpi": config.FIGURE_DPI,
        "canvas_inches": [16, 9],
        "theme": config.THEME_NAME,
        "cleaning": data["provenance"],
    }
    digest = hashlib.sha256(
        json.dumps(settings, sort_keys=True).encode() + Path(config.__file__).read_bytes()
    ).hexdigest()[:8]
    source = viz.load_theme().source_line(
        f"原神抽卡公开记录·清洗库（DS{dataset:02d}；Q01含其他来源）",
        "make_charts.py",
        f"{config.CHART_CONFIG_VERSION}+{digest} / 清洗{data['provenance']['rule_version']}",
    )
    figures = []
    for filename, plot in PLOTS:
        progress(filename)
        fig = plot(data, source)
        title = fig._dsh_title
        path = viz.save(fig, output / f"{filename}.png", ppt=True)
        figures.append({"file": path.name, "title": title, "pixels": [3200, 1800], "dpi": 200})
    modules = [
        Path(__file__),
        Path(__file__).with_name("ads.py"),
        Path(config.__file__),
        Path(viz.__file__),
        Path(viz.__file__).with_name("plots.py"),
        config.PROJECT_ROOT / "make_charts.py",
        config.PROJECT_ROOT / "theme/theme.py",
        config.PROJECT_ROOT / "theme/spec_check.py",
    ]
    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "settings": settings,
        "config_hash": digest,
        "source_file": database.name,
        "source_bytes": database.stat().st_size,
        "source_mtime_ns": database.stat().st_mtime_ns,
        "python": platform.python_version(),
        "matplotlib": matplotlib.__version__,
        "numpy": version("numpy"),
        "pandas": version("pandas"),
        "fonts": fonts,
        "figures": figures,
        "code_sha256": {
            str(path.relative_to(config.PROJECT_ROOT)): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in modules
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    scope = data["scope"]
    report = [
        "# 原神留存抽卡记录分析",
        "",
        f"主分析 DS{dataset:02d}：{scope['people']:,} 个账号，{scope['pulls']:,} 抽。",
        f"记录范围：{scope['first_time']}—{scope['last_time']}（时区未知）。",
        "",
        "这是所提供公开记录的描述性分析；来源内去重，不代表全部玩家。抽数不能换算付费或活跃；记录可能缺失。",
        "不使用待复核物品类型做分类，不合并多语言名称；记录内五星占比和间隔不能替代官方概率或保底规则。",
        "",
        "## 图表与结论",
        "",
    ]
    for figure in figures:
        if figure["file"].startswith("Q01_"):
            continue
        report += [f"### {figure['title']}", "", f"![{figure['title']}]({figure['file']})", ""]
    report += [
        "## 复现与保护",
        "",
        "在项目根目录运行 `python make_charts.py --database <清洗库路径>`。未安装包时先设置 `PYTHONPATH=src;.`。",
        "入口通过本地 import 调用 ADS、绘图和主题；首次运行需安装项目的 analysis、viz 依赖及开源中文字体。",
        f"配置：{config.CHART_CONFIG_VERSION}+{digest}；全部为16:9、3200×1800像素、200 dpi；保存前执行主题自检。",
        "不足5个贡献账号的格子在ADS置空并做互补抑制；分布合并相邻箱。月份、名称与间隔分箱的贡献人数使用保守下界。",
        "ADS不含账号或抽卡标识；输入清洗库只读。复现信息见 manifest.json，发布的聚合见 ads.json。",
        "",
    ]
    (output / "分析报告.md").write_text("\n".join(report), encoding="utf-8")
    progress("完成")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="使用本地蓝粉主题生成完整原神分析图集，无双Y轴。")
    parser.add_argument("--database", type=Path, help="默认取本项目最新的清洗库")
    parser.add_argument("--output", type=Path, help="项目内尚不存在的输出目录")
    parser.add_argument("--dataset", type=int, default=3, help="主分析来源，默认03")
    args = parser.parse_args(argv)
    output = generate(args.database, args.output, args.dataset)
    print(json.dumps({"output": str(output), "figures": 8}, ensure_ascii=False))
    return 0
