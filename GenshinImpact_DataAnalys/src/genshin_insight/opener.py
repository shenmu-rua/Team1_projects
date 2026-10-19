"""只复用发布ADS，制作可离线播放的答辩开场视频。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from . import config
from .ads import MIN_PEOPLE, POOL_NAMES
from .defense import embed_font, load_release
from .score import synthesize

BACKGROUND_PROMPT = (
    "Create a cinematic widescreen 16:9 background plate for an elegant Chinese academic "
    "data-analysis opening film about Genshin gacha records. Use case: abstract fantasy "
    "cosmic environment / motion-design background, NOT an infographic. Rich near-black "
    "midnight indigo space, sweeping delicate champagne-gold and ice-blue meteor trails "
    "along the lower third and outer edges, tiny luminous star dust, subtle violet nebula "
    "volume, a large elegant luminous wish-like streak travelling diagonally into the "
    "distance. Premium blockbuster title-sequence quality, beautiful volumetric light and "
    "refined restrained gold, dimensional depth, sharp fine details, no cartoon. Reserve "
    "the broad central 70% of the image as very dark, calm negative space for large data "
    "typography and charts to be added later. Left-center must especially remain dark and "
    "uncluttered. No text, letters, numbers, logos, icons, data charts, interface panels, "
    "people, recognizable characters, or watermark. Full bleed 3840x2160 composition if possible."
)

SCENES = [
    (0, 4, "片头"),
    (4, 10, "主分析记录规模"),
    (10, 16, "卡池构成"),
    (16, 23, "月度峰值"),
    (23, 29, "账号记录量"),
    (29, 35, "五星原始名称"),
    (35, 40, "答辩标题"),
]


def summarize(data: dict) -> dict:
    """只选受保护指标，数字完全来自同一次发布，不连接数据库。"""
    scope = data["scope"]
    if scope.get("suppressed") or scope["people"] < MIN_PEOPLE:
        raise ValueError("记录规模未达到发布门槛。")
    pools = sorted(data["pools"], key=lambda row: row["pulls"], reverse=True)
    if any(row.get("suppressed") or row["people"] < MIN_PEOPLE for row in pools):
        raise ValueError("卡池构成包含隐藏格。")
    if sum(row["pulls"] for row in pools) != scope["pulls"]:
        raise ValueError("卡池构成与记录总量不一致。")
    months = sorted(
        (row for row in data["months"] if row["pool_group"] == 301), key=lambda row: row["month"]
    )
    safe_months = [
        row for row in months if not row.get("suppressed") and row["people"] >= MIN_PEOPLE
    ]
    peak = max(safe_months, key=lambda row: row["pulls"])
    bins = [
        {"lo": row["lo"], "hi": row["hi"], "count": row["counts"][0]}
        for row in data["volume_bins"]
        if row["people"][0] >= MIN_PEOPLE
    ]
    if sum(row["count"] for row in bins) != scope["people"]:
        raise ValueError("账号分箱与账号总数不一致。")
    items = [
        row for row in data["items"] if not row.get("suppressed") and row["people"] >= MIN_PEOPLE
    ][:5]
    if not items:
        raise ValueError("缺少可发布的名称汇总。")
    return {
        "pulls": scope["pulls"],
        "people": scope["people"],
        "first": scope["first_time"][:10],
        "last": scope["last_time"][:10],
        "median": data["volume_median"],
        "roleShare": 100
        * next(row["pulls"] for row in pools if row["pool_group"] == 301)
        / scope["pulls"],
        "pools": [
            {
                "name": POOL_NAMES[row["pool_group"]],
                "count": row["pulls"],
                "pool": row["pool_group"],
            }
            for row in pools
        ],
        "months": [
            {"month": row["month"], "count": row["pulls"] if row in safe_months else None}
            for row in months
        ],
        "peak": {"month": peak["month"], "count": peak["pulls"]},
        "bins": bins,
        "items": [{"name": row["name"], "count": row["pulls"]} for row in items],
    }


def render(output: Path, ffmpeg: str | None = None, node: str | None = None) -> None:
    """本地Chrome逐帧渲染、WebCodecs编码，再封装通用H.264/AAC MP4。"""
    if ffmpeg is None:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    node = node or shutil.which("node")
    if node is None:
        raise FileNotFoundError("需要Node.js及本地playwright包。")
    subprocess.run(
        [node, str(Path(__file__).with_name("viz") / "render_opener.cjs"), str(output), ffmpeg],
        check=True,
    )


def build(
    analysis: Path,
    output: Path,
    background: Path,
    *,
    prepare_only=False,
    replace=False,
    ffmpeg=None,
    node=None,
) -> Path:
    """生成独立MP4、动画母版、配乐、离线答辩入口及来源清单。"""
    analysis, output, background = (
        analysis.resolve(strict=True),
        output.resolve(),
        background.resolve(strict=True),
    )
    if not all(path.is_relative_to(config.PROJECT_ROOT.resolve()) for path in (analysis, output)):
        raise ValueError("分析输入与输出必须位于本项目内部。")
    if output.exists() and not (replace and (output / "build_manifest.json").is_file()):
        raise FileExistsError("输出已存在；只允许显式更新已有开场片目录。")
    data, audit, manifest = load_release(analysis)
    metrics = summarize(data)
    template = Path(__file__).with_name("viz") / "opener.html"
    html = template.read_text(encoding="utf-8")
    footer = f"主分析03  清洗{audit['rule_version']}  图表{manifest['settings']['version']}+{manifest['config_hash']}"
    for key, value in {
        "DATA": json.dumps(metrics, ensure_ascii=False).replace("</", "<\\/"),
        "SCENES": json.dumps(SCENES, ensure_ascii=False),
        "BACKGROUND": base64.b64encode(background.read_bytes()).decode("ascii"),
        "FOOTER": footer,
    }.items():
        html = html.replace(f"__{key}__", value)
    output.mkdir(parents=True, exist_ok=replace)
    assets = output / "assets"
    assets.mkdir(exist_ok=replace)
    if background != (assets / "cosmic-background.png").resolve():
        shutil.copy2(background, assets / "cosmic-background.png")
    player = (template.parent / "opener_player.html").read_text(encoding="utf-8")
    font, notice = embed_font(html + player, assets / "noto-sans-sc-subset.woff")
    html = html.replace("__FONT__", font).replace(
        "__FONT_LICENSE__", notice.replace("</script", "<\\/script")
    )
    (output / "motion.html").write_text(html, encoding="utf-8")
    (output / "index.html").write_text(
        player.replace("__FONT__", font),
        encoding="utf-8",
    )
    synthesize(output / "原创配乐.wav")
    storyboard = [
        "# 答辩开场视频",
        "",
        "40秒，1920×1080，30fps。原创合成配乐，无旁白。画面仅使用已发布ADS。",
        "",
        "| 时间 | 内容 |",
        "| --- | --- |",
    ]
    storyboard += [f"| {start:02}–{end:02}秒 | {title} |" for start, end, title in SCENES]
    storyboard += [
        "",
        "从index.html开始播放，片尾自动进入相邻defense_20261019_final目录的32页答辩。可跳过片头。MP4可单独播放或插入其他PPT。",
        "",
        "规模、卡池、月度峰值、账号中位数、名称榜均与答辩采用同次受保护聚合。名称按原始字符串精确汇总，未合并翻译别名；账号记录量不等于付费；留存记录无法推断官方概率或保底。",
        "",
        "背景为imagegen内置工具生成的装饰星空，不表示账号或统计点；字体为SIL OFL许可Noto Sans SC，许可附在assets。配乐由本项目score.py原创合成，无外部音频采样。",
        "",
        "背景保存于assets/cosmic-background.png，使用imagegen内置工具生成。最终生成提示词如下：",
        "",
        BACKGROUND_PROMPT,
    ]
    (output / "使用说明.md").write_text("\n".join(storyboard), encoding="utf-8")
    metadata = {
        "video_version": "1.0.0",
        "duration_seconds": 40,
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "scenes": SCENES,
        "dataset": data["dataset"],
        "source_config": manifest["config_hash"],
        "source_ads_sha256": hashlib.sha256((analysis / "ads.json").read_bytes()).hexdigest(),
        "background_sha256": hashlib.sha256(background.read_bytes()).hexdigest(),
        "background_generation": "imagegen built-in tool",
        "background_prompt": BACKGROUND_PROMPT,
        "music": "Original local synthesis; no voice or external samples",
        "metrics": metrics,
        "code_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                Path(__file__),
                Path(__file__).with_name("score.py"),
                template,
                template.parent / "render_opener.cjs",
                template.parent / "opener_player.html",
            ]
        },
    }
    (output / "build_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not prepare_only:
        render(output, ffmpeg, node)
    return output / "index.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从发布ADS制作40秒答辩开场视频，不读取数据库。")
    parser.add_argument(
        "--analysis", type=Path, default=config.IMAGE_DIR / "analysis_20261019_final"
    )
    parser.add_argument(
        "--output", type=Path, default=config.PRESENTATION_DIR / "opener_20261019_final"
    )
    parser.add_argument("--background", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--node")
    args = parser.parse_args(argv)
    print(
        build(
            args.analysis,
            args.output,
            args.background,
            prepare_only=args.prepare_only,
            replace=args.replace,
            ffmpeg=args.ffmpeg,
            node=args.node,
        )
    )
    return 0
