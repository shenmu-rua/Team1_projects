"""只复用发布ADS，制作可离线播放的答辩开场视频。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config
from .ads import MIN_PEOPLE, POOL_NAMES
from .defense import embed_font, load_release, logo_svg

SOURCE_END = 116.4
GRAPHICS_DURATION = 40.0
WHITE_TAIL_DURATION = 1.2
VIDEO_FPS = 60

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


def video_timing(source_end: float = SOURCE_END) -> dict:
    """倒推裁切点；图表40秒后清空，保留视频自身的入门白场。"""
    duration = GRAPHICS_DURATION + WHITE_TAIL_DURATION
    if not math.isfinite(source_end) or source_end < duration:
        raise ValueError("白场结束时间必须有限，且不能早于开场总时长。")
    return {
        "duration": duration,
        "graphicsDuration": GRAPHICS_DURATION,
        "fadeStart": GRAPHICS_DURATION - 0.4,
        "whiteAt": duration - 0.2,
        "sourceStart": round(source_end - duration, 6),
        "sourceEnd": source_end,
        "fps": VIDEO_FPS,
    }


def ffmpeg_executable(ffmpeg: str | None = None) -> str:
    if ffmpeg is None:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    return ffmpeg


def prepare_video(source: Path, target: Path, timing: dict, ffmpeg: str) -> None:
    """精确裁切指定视频及同段原声，不添加背景动画或原创配乐。"""
    temporary = target.with_name("background.partial.mp4")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(timing["sourceStart"]),
            "-i",
            str(source),
            "-t",
            str(timing["duration"]),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "17",
            "-r",
            str(timing["fps"]),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "320k",
            "-ar",
            "48000",
            "-af",
            f"afade=t=in:st=0:d=0.03,afade=t=out:st={timing['whiteAt']}:d=0.2",
            "-map_metadata",
            "-1",
            "-movflags",
            "+faststart",
            str(temporary),
        ],
        check=True,
    )
    temporary.replace(target)


def render(
    output: Path, ffmpeg: str | None = None, node: str | None = None, work: Path | None = None
) -> None:
    """Chrome导出透明图表，由FFmpeg叠加60fps背景并保留原声。"""
    ffmpeg = ffmpeg_executable(ffmpeg)
    node = node or shutil.which("node")
    if node is None:
        raise FileNotFoundError("需要Node.js及本地playwright包。")
    arguments = [
        node,
        str(Path(__file__).with_name("viz") / "render_opener.cjs"),
        str(output),
        ffmpeg,
    ]
    if work is not None:
        arguments += ["--work", str(work)]
    subprocess.run(arguments, check=True)


def build(
    analysis: Path,
    output: Path,
    background: Path,
    *,
    prepare_only=False,
    replace=False,
    ffmpeg=None,
    node=None,
    source_end=SOURCE_END,
) -> Path:
    """交付单份压缩MP4及播放入口，构建中间文件只写项目缓存。"""
    analysis, output, background = (
        analysis.resolve(strict=True),
        output.resolve(),
        background.resolve(strict=True),
    )
    if not all(path.is_relative_to(config.PROJECT_ROOT.resolve()) for path in (analysis, output)):
        raise ValueError("分析输入与输出必须位于本项目内部。")
    if output.exists() and not (replace and (output / "build_manifest.json").is_file()):
        raise FileExistsError("输出已存在；只允许显式更新已有开场片目录。")
    timing = video_timing(source_end)
    ffmpeg = ffmpeg_executable(ffmpeg)
    data, audit, manifest = load_release(analysis)
    metrics = summarize(data)
    template = Path(__file__).with_name("viz") / "opener.html"
    html = template.read_text(encoding="utf-8")
    logo_metadata = json.loads((template.parent / "genshin_logo.json").read_text(encoding="utf-8"))
    logo_markup = logo_svg()
    logo = {
        "src": "data:image/png;base64,"
        + base64.b64encode((template.parent / logo_metadata["asset"]).read_bytes()).decode("ascii"),
        "bounds": logo_metadata["visible_bounds"],
        "aspect": logo_metadata["display_aspect_ratio"],
    }
    footer = f"主分析03  清洗{audit['rule_version']}  图表{manifest['settings']['version']}+{manifest['config_hash']}"
    for key, value in {
        "DATA": json.dumps(metrics, ensure_ascii=False).replace("</", "<\\/"),
        "SCENES": json.dumps(SCENES, ensure_ascii=False),
        "TIMING": json.dumps(timing),
        "LOGO": json.dumps(logo),
        "FOOTER": footer,
    }.items():
        html = html.replace(f"__{key}__", value)
    output.mkdir(parents=True, exist_ok=replace)
    cache = (config.PROJECT_ROOT / ".pytest_cache").resolve()
    if not cache.is_relative_to(config.PROJECT_ROOT.resolve()):
        raise ValueError("构建缓存必须位于本项目内部。")
    cache.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="opener-build-", dir=cache)).resolve()
    assets = work / "assets"
    assets.mkdir()
    prepare_video(background, assets / "background.mp4", timing, ffmpeg)
    player = (template.parent / "opener_player.html").read_text(encoding="utf-8")
    player = player.replace("__GENSHIN_LOGO__", logo_markup)
    font, notice = embed_font(html + player, assets / "noto-sans-sc-subset.woff")
    html = html.replace("__FONT__", font).replace(
        "__FONT_LICENSE__", notice.replace("</script", "<\\/script")
    )
    (work / "motion.html").write_text(html, encoding="utf-8")
    (output / "assets").mkdir(exist_ok=True)
    shutil.copyfile(assets / "FONT_LICENSE.txt", output / "assets/FONT_LICENSE.txt")
    (output / "index.html").write_text(
        player.replace("__FONT__", font).replace("__TIMING__", json.dumps(timing)),
        encoding="utf-8",
    )
    storyboard = [
        "# 答辩开场视频",
        "",
        "图表展示40秒，接1.2秒视频自身的入门白场，总长41.2秒，1920×1080，60fps。",
        "片头和片尾标题中的原神采用官方原始标识，显示为白色艺术字，并沿用对应标题的发光效果。",
        "背景和声音均来自用户提供的视频；图表仅使用已发布ADS。未叠加旧星空、缩放、光晕或背景漂移动效。",
        "",
        "| 时间 | 内容 |",
        "| --- | --- |",
    ]
    storyboard += [f"| {start:02}–{end:02}秒 | {title} |" for start, end, title in SCENES]
    storyboard += ["| 40–41.2秒 | 仅保留视频自然入门白场，所有图表、文字、遮罩和按钮均隐藏 |"]
    storyboard += [
        "",
        "从index.html开始播放，片尾自动进入相邻defense_20261019_final目录的完整答辩（含四人分工）。可跳过片头。MP4可单独播放或插入其他PPT。",
        "",
        "规模、卡池、月度峰值、账号中位数、名称榜均与答辩采用同次受保护聚合。名称按原始字符串精确汇总，未合并翻译别名；账号记录量不等于付费；留存记录无法推断官方概率或保底。",
        "",
        f"背景从原视频{timing['sourceStart']:.3f}秒裁到{timing['sourceEnd']:.3f}秒，原速播放。",
        "图表前景39.6–40秒淡出；40秒起透明清空，背景不再有暗化遮罩。41秒起已全白，41.2秒时无黑帧接入预加载的答辩。",
        "使用同段视频原声，仅在首尾做极短音量淡入淡出以避免切口爆音，没有混入原开场配乐。",
        "字体为SIL OFL许可Noto Sans SC，许可附在assets。",
        "",
        "交付目录仅保留成片、播放入口、海报、使用说明、构建清单和字体许可。",
        "成片采用H.264 CRF 23 / slow、AAC 160k，保留1080p与60fps。",
        "背景视频、透明前景母版和字体子集只用于构建，位于项目缓存，完成构建后自动删除。",
    ]
    (output / "使用说明.md").write_text("\n".join(storyboard), encoding="utf-8")
    metadata = {
        "video_version": "2.2.0",
        "video_wordmark": {
            "source_url": logo_metadata["source_url"],
            "asset_sha256": logo_metadata["sha256"],
            "color": "#FFFFFF",
            "glow_blur_pixels": {"intro": 25, "ending": 15},
            "scenes_seconds": [[0, 4], [35, 40]],
        },
        "duration_seconds": timing["duration"],
        "graphics_duration_seconds": GRAPHICS_DURATION,
        "width": 1920,
        "height": 1080,
        "fps": VIDEO_FPS,
        "encoding": {"video": "H.264", "preset": "slow", "crf": 23, "audio": "AAC 160k"},
        "timing": timing,
        "scenes": SCENES,
        "dataset": data["dataset"],
        "source_config": manifest["config_hash"],
        "source_ads_sha256": hashlib.sha256((analysis / "ads.json").read_bytes()).hexdigest(),
        "source_video": background.name,
        "source_video_sha256": hashlib.sha256(background.read_bytes()).hexdigest(),
        "background_sha256": hashlib.sha256((assets / "background.mp4").read_bytes()).hexdigest(),
        "background_motion": "User-provided video at original speed; no added background animation",
        "music": "Original audio from the same source-video interval; short edge fades only",
        "metrics": metrics,
        "code_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                Path(__file__),
                template,
                template.parent / "render_opener.cjs",
                template.parent / "opener_player.html",
            ]
        },
    }
    (output / "build_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if prepare_only:
        return work / "motion.html"
    try:
        render(output, ffmpeg, node, work)
        metadata["output_video_sha256"] = hashlib.sha256(
            (output / "开场视频.mp4").read_bytes()
        ).hexdigest()
        metadata["output_video_bytes"] = (output / "开场视频.mp4").stat().st_size
        (output / "build_manifest.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    finally:
        if work.parent != cache or not work.is_relative_to(config.PROJECT_ROOT.resolve()):
            raise ValueError("拒绝清理项目缓存以外的路径。")
        shutil.rmtree(work)
    return output / "index.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="genshin-insight opener", description="40秒ADS图表叠加原声视频，入门全白后进入答辩。"
    )
    parser.add_argument(
        "--analysis", type=Path, default=config.IMAGE_DIR / "analysis_20261019_final"
    )
    parser.add_argument(
        "--output", type=Path, default=config.PRESENTATION_DIR / "opener_20261019_final"
    )
    parser.add_argument(
        "--background-video", "--background", dest="background", type=Path, required=True
    )
    parser.add_argument("--source-end", type=float, default=SOURCE_END, help="源视频的白场结束秒数")
    parser.add_argument(
        "--prepare-only", action="store_true", help="仅在项目缓存生成可定位的动画母版"
    )
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
            source_end=args.source_end,
        )
    )
    return 0
