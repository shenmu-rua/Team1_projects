"""将启动标识片段接到已有开场，并将末帧对齐现有答辩首页。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

from . import config
from .defense import embed_font, logo_svg
from .opener import ffmpeg_executable, measure_flash


def relative_url(target: Path, directory: Path) -> str:
    """用相对链接保持视频入口和答辩可一起移动。"""
    target, directory = target.resolve(), directory.resolve()
    shared = 0
    for left, right in zip(target.parts, directory.parts, strict=False):
        if left.casefold() != right.casefold():
            break
        shared += 1
    if not shared:
        raise ValueError("视频入口和答辩必须位于同一个项目磁盘。")
    return quote("/".join([".."] * (len(directory.parts) - shared) + list(target.parts[shared:])))


def build(
    base: Path,
    logo_video: Path,
    deck: Path,
    output: Path,
    *,
    source_url: str = "",
    source_duration: float = 2.0,
    move_duration: float = 1.6,
    hold_duration: float = 0.6,
    replace: bool = False,
    ffmpeg: str | None = None,
    node: str | None = None,
) -> Path:
    """只重绘新转场，既有开场的视频和音频流直接拼接。"""
    base, logo_video, deck = (path.resolve(strict=True) for path in (base, logo_video, deck))
    output, root = output.resolve(), config.PROJECT_ROOT.resolve()
    if not deck.is_relative_to(root) or not output.is_relative_to(root):
        raise ValueError("答辩与输出必须位于本项目内部。")
    if (
        not all(
            math.isfinite(value) and value > 0
            for value in (source_duration, move_duration, hold_duration)
        )
        or source_duration < 0.5
    ):
        raise ValueError("转场时长必须有限且大于零，素材片段至少0.5秒。")
    if output.exists() and not (replace and (output / "build_manifest.json").is_file()):
        raise FileExistsError("输出已存在；只允许显式更新已有开场片目录。")
    source_manifest = base.parent / "build_manifest.json"
    metadata = (
        json.loads(source_manifest.read_text(encoding="utf-8")) if source_manifest.is_file() else {}
    )
    base_hash = hashlib.sha256(base.read_bytes()).hexdigest()
    if metadata.get("logo_transition") and metadata.get("output_video_sha256") == base_hash:
        raise ValueError("此成片已包含标识转场，请指定未拼接的基础开场视频。")
    cache = (root / ".pytest_cache").resolve()
    if cache.parent != root:
        raise ValueError("构建缓存必须位于本项目内部。")
    cache.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="opener-transition-", dir=cache)).resolve()
    template = Path(__file__).with_name("viz")
    node = node or shutil.which("node")
    if node is None:
        raise FileNotFoundError("需要Node.js及本地playwright包。")
    try:
        subprocess.run(
            [
                node,
                str(template / "render_transition.cjs"),
                str(base),
                str(logo_video),
                str(deck),
                str(work),
                ffmpeg_executable(ffmpeg),
                str(source_duration),
                str(move_duration),
                str(hold_duration),
            ],
            check=True,
        )
        result = json.loads((work / "transition_metadata.json").read_text(encoding="utf-8"))
        timing = dict(metadata.get("timing", {}))
        timing.update(
            duration=result["duration"],
            graphicsDuration=timing.get("graphicsDuration", 40.0),
            whiteAt=timing.get("whiteAt", result["baseDuration"] - 0.2),
            flashExpandStart=timing.get(
                "flashExpandStart", round(result["baseDuration"] - 0.65, 6)
            ),
            flashExpandEnd=timing.get("flashExpandEnd", round(result["baseDuration"] - 0.25, 6)),
            logoTransition={
                "start": result["baseDuration"],
                "sourceDuration": source_duration,
                "moveDuration": move_duration,
                "holdDuration": hold_duration,
            },
        )
        timing["flashProfile"] = measure_flash(
            work / "combined.mp4", ffmpeg_executable(ffmpeg), timing
        )
        timing["flashExpandStart"] = timing["flashProfile"]["curve"][0][0]
        timing["flashExpandEnd"] = timing["flashProfile"]["curve"][-1][0]
        assets = work / "assets"
        assets.mkdir()
        player = (template / "opener_player.html").read_text(encoding="utf-8")
        player = player.replace("__GENSHIN_LOGO__", logo_svg())
        font, _ = embed_font(player, assets / "noto-sans-sc-subset.woff")
        player = player.replace("__FONT__", font).replace("__TIMING__", json.dumps(timing))
        player = player.replace("../defense_20261019_final/index.html", relative_url(deck, output))
        metadata.update(
            video_version="2.3.0",
            duration_seconds=result["duration"],
            timing=timing,
            base_output_video_sha256=base_hash,
            output_video_sha256=hashlib.sha256((work / "combined.mp4").read_bytes()).hexdigest(),
            output_video_bytes=(work / "combined.mp4").stat().st_size,
            logo_transition={
                "source_url": source_url,
                "source_video": logo_video.name,
                "source_video_sha256": hashlib.sha256(logo_video.read_bytes()).hexdigest(),
                "source_segment_seconds": [0, source_duration],
                "start_seconds": result["baseDuration"],
                "move_duration_seconds": move_duration,
                "final_hold_seconds": hold_duration,
                "prompt_hidden": result["maskedPrompt"],
                "source_logo_box": result["sourceBounds"],
                "cover_logo_box": result["target"],
                "deck_sha256": hashlib.sha256(deck.read_bytes()).hexdigest(),
                "cover_slide_count": result["slideCount"],
                "original_segment_reencoded": False,
            },
            transition_code_sha256={
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (
                    Path(__file__),
                    template / "render_transition.cjs",
                    template / "opener_transition.html",
                    template / "opener_player.html",
                )
            },
        )
        verification = metadata.setdefault("verification", {})
        for name in ("audio_unchanged_from_previous_video", "audio_sha256"):
            verification.pop(name, None)
        verification.update(
            transition_probes=len(result["probes"]),
            source_prompt_hidden=True,
            cover_alignment_verified=True,
            mp4_full_decode_verified=result["fullDecodeVerified"],
        )
        metadata["player_branding"] = {
            "color": "#FFFFFF",
            "player_sha256": hashlib.sha256(player.encode("utf-8")).hexdigest(),
            "template_sha256": hashlib.sha256(
                (template / "opener_player.html").read_bytes()
            ).hexdigest(),
        }
        qa = cache / "opener_transition_qa"
        qa.mkdir(exist_ok=True)
        for path in (
            *work.glob("preview_*.png"),
            work / "transition_metadata.json",
            work / "cover.png",
        ):
            shutil.copy2(path, qa / path.name)
        output.mkdir(parents=True, exist_ok=replace)
        (output / "assets").mkdir(exist_ok=True)
        shutil.copy2(assets / "FONT_LICENSE.txt", output / "assets/FONT_LICENSE.txt")
        if (base.parent / "poster.jpg").is_file() and base.parent != output:
            shutil.copy2(base.parent / "poster.jpg", output / "poster.jpg")
        (work / "combined.mp4").replace(output / "开场视频.mp4")
        (output / "index.html").write_text(player, encoding="utf-8", newline="\n")
        (output / "build_manifest.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output / "使用说明.md").write_text(
            "# 答辩开场视频\n\n"
            "原有40秒图表与白色发光艺术字保留。入门白场后接入指定启动素材，隐藏标识下方提示文字。\n"
            "播放器按成片逐帧白光覆盖率连续放大视频至铺满窗口，仅在稳定白场内恢复比例；"
            "底色与成片边缘颜色同步。播放不自动请求浏览器全屏。\n"
            f"{result['baseDuration']:.1f}秒开始出现白底原神标识，"
            f"{result['baseDuration'] + source_duration:.1f}秒开始缩小、移动并渐显答辩首页，"
            f"{result['duration']:.1f}秒切入可翻页的完整答辩。\n\n"
            f"素材来源：{source_url}\n\n"
            f"标识最终位置直接测量现有首页，与{result['slideCount']}页答辩保持一致。"
            "打开index.html播放，片尾无白屏闪回地接入实时答辩；也可跳过片头。\n"
            "MP4包含完整转场与首页停留画面，可独立播放。仅新转场重新编码，既有开场视频与音轨直接拼接。\n"
            "保持1920×1080、60fps、H.264/AAC。若修改首页版式，需重新制作转场以保持位置一致。\n"
            "字体为SIL OFL许可Noto Sans SC，许可附在assets。\n",
            encoding="utf-8",
        )
    finally:
        if work.parent != cache or not work.is_relative_to(root):
            raise ValueError("拒绝清理项目缓存以外的路径。")
        shutil.rmtree(work)
    return output / "index.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="genshin-insight opener-transition", description="白场标识缩小移动并衔接现有答辩首页。"
    )
    parser.add_argument("--opener", type=Path, required=True)
    parser.add_argument("--logo-video", type=Path, required=True)
    parser.add_argument("--deck", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-duration", type=float, default=2.0)
    parser.add_argument("--move-duration", type=float, default=1.6)
    parser.add_argument("--hold-duration", type=float, default=0.6)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--node")
    args = parser.parse_args(argv)
    print(
        build(
            args.opener,
            args.logo_video,
            args.deck,
            args.output,
            source_url=args.source_url,
            source_duration=args.source_duration,
            move_duration=args.move_duration,
            hold_duration=args.hold_duration,
            replace=args.replace,
            ffmpeg=args.ffmpeg,
            node=args.node,
        )
    )
    return 0
