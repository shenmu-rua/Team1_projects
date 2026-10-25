"""从已发布的受保护聚合制作离线交互大屏；不连接数据库。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config

SECTIONS = (
    "dataset",
    "scope",
    "provenance",
    "checks",
    "pools",
    "months",
    "clock",
    "volume_bins",
    "volume_median",
    "rates",
    "gap_bins",
    "gap_quality",
    "items",
    "privacy",
)
FIELDS = {
    "scope": {"dataset_id", "pulls", "people", "first_time", "last_time", "suppressed"},
    "provenance": {"config_version", "rule_version"},
    "checks": {"failed", "checks"},
    "pools": {"pool_group", "pulls", "people", "star5", "suppressed"},
    "months": {"pool_group", "month", "pulls", "people", "suppressed"},
    "clock": {"weekday", "hour", "pulls", "people", "suppressed"},
    "volume_bins": {"lo", "hi", "counts", "people"},
    "rates": {"pool_group", "quartile", "groups", "people", "q25", "median", "q75"},
    "gap_bins": {"lo", "hi", "counts", "people"},
    "gap_quality": {
        "player_pools",
        "eligible_player_pools",
        "ambiguous_pulls",
        "item_type_review_pulls",
    },
    "items": {"name", "pulls", "people"},
    "privacy": {"minimum_people", "people_semantics"},
}


def load_aggregates(analysis: Path) -> dict:
    """允许清单投影，拒绝小样本泄露；隐藏月格保持空值，禁止回填。"""
    data = json.loads((analysis / "ads.json").read_text(encoding="utf-8"))
    if data.get("dataset") != 3 or data.get("privacy", {}).get("minimum_people", 0) < 5:
        raise ValueError("大屏仅接收DS03且发布门槛至少为5的受保护ADS。")
    if data.get("checks", {}).get("failed") != 0 or data["scope"].get("suppressed"):
        raise ValueError("聚合稽核未通过或主范围被抑制，停止发布。")

    def project(section: str, row: dict) -> dict:
        return {key: value for key, value in row.items() if key in FIELDS[section]}

    safe = {}
    for section in SECTIONS:
        value = data[section]
        if section == "gap_bins":
            safe[section] = {
                pool: [project(section, row) for row in bins]
                for pool, bins in value.items()
                if pool in {"200", "301", "302"}
            }
        elif isinstance(value, list):
            safe[section] = [project(section, row) for row in value]
        elif isinstance(value, dict):
            safe[section] = project(section, value)
        else:
            safe[section] = value
    threshold = safe["privacy"]["minimum_people"]
    if safe["scope"]["people"] < threshold:
        raise ValueError("主分析账号数未达到发布门槛。")
    if any(row.get("suppressed") for row in safe["pools"]):
        raise ValueError("主卡池总量必须全部达到发布门槛，不能回推隐藏总量。")
    if sum(row["pulls"] for row in safe["pools"]) != safe["scope"]["pulls"]:
        raise ValueError("卡池与主分析记录总量不一致。")
    if sum(row["counts"]["0"] for row in safe["volume_bins"]) != safe["scope"]["people"]:
        raise ValueError("账号安全分箱与主分析账号总量不一致。")
    for section in ("pools", "months", "clock", "rates", "items"):
        for row in safe[section]:
            if row.get("suppressed"):
                measures = ("pulls", "people", "star5", "q25", "median", "q75")
                if any(row.get(key) is not None for key in measures):
                    raise ValueError("抑制格仍包含统计值，拒绝构建。")
            elif row["people"] < threshold:
                raise ValueError("发布聚合未达到贡献账号门槛。")
    for section in ("volume_bins", "gap_bins"):
        groups = [safe[section]] if section == "volume_bins" else safe[section].values()
        for bins in groups:
            for row in bins:
                allowed = {"0"} if section == "volume_bins" else {"200", "301", "302"}
                for field in ("counts", "people"):
                    row[field] = {key: value for key, value in row[field].items() if key in allowed}
                if any(value < threshold for value in row["people"].values()):
                    raise ValueError("发布分箱未达到贡献账号门槛。")
    if any(re.search(r"\d{8,}", row["name"]) for row in safe["items"]):
        raise ValueError("名称聚合包含疑似个人标识。")
    return safe


def theme_tokens() -> dict:
    """网页颜色沿用项目唯一主题实现及固定卡池映射。"""
    from .viz import load_theme
    from .viz.plots import pool_colors

    theme = load_theme()
    names = {
        "bg": "BG",
        "panel": "PANEL",
        "surface": "SURFACE",
        "grid": "GRID",
        "axis": "AXIS",
        "ink": "INK",
        "soft": "INK_SOFT",
        "muted": "MUTED",
        "faint": "FAINT",
        "pink": "MAIN",
        "pink-light": "PINK_100",
        "pink-dark": "PINK_700",
        "blue": "PAST",
        "blue-light": "BLUE_100",
        "violet": "BRIDGE",
        "green": "GREEN",
        "amber": "AMBER",
    }
    return {
        **{name: getattr(theme, key) for name, key in names.items()},
        **{f"pool-{pool}": color for pool, color in pool_colors().items()},
    }


def build(
    analysis: Path | None = None, output: Path | None = None, *, replace: bool = False
) -> Path:
    """构建可单独复制的HTML；默认拒绝覆盖任何已有目录。"""
    analysis = (analysis or config.IMAGE_DIR / "analysis_20261019_final").resolve(strict=True)
    now = datetime.now(timezone(timedelta(hours=8)))
    output = (output or config.PRESENTATION_DIR / f"dashboard_{now:%Y%m%d_%H%M%S}").resolve()
    root = config.PROJECT_ROOT.resolve()
    if not all(path.is_relative_to(root) for path in (analysis, output)):
        raise ValueError("输入与输出必须位于本项目目录。")
    if output.exists():
        marker = output / "build_manifest.json"
        if not replace or not marker.is_file():
            raise FileExistsError("目标已存在；仅允许显式替换带大屏构建清单的目录。")
        if "dashboard_version" not in json.loads(marker.read_text(encoding="utf-8")):
            raise ValueError("目标目录不是大屏交付目录，拒绝覆盖。")
    data = load_aggregates(analysis)
    palette = theme_tokens()
    data["display"] = {
        "version": config.DASHBOARD_VERSION,
        "ads_sha256": hashlib.sha256((analysis / "ads.json").read_bytes()).hexdigest(),
        "built_at": now.isoformat(timespec="seconds"),
        "colors": {pool: palette[f"pool-{pool}"] for pool in (100, 200, 301, 302)},
        "heat_palette": [palette["pink-light"], palette["pink"], palette["pink-dark"]],
    }
    templates = Path(__file__).with_name("viz")
    html = (templates / "dashboard.html").read_text(encoding="utf-8")
    css = (templates / "dashboard.css").read_text(encoding="utf-8")
    script = (templates / "dashboard.js").read_text(encoding="utf-8")
    tokens = ":root{" + "".join(f"--{k}:{v};" for k, v in palette.items()) + "}"
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    html = html.replace("__STYLE__", tokens + css).replace("__SCRIPT__", script)
    html = html.replace("__DATA__", encoded)
    # 直接复用既有字体子集化函数，字体许可与字体一起嵌入，页面无需CDN。
    from .defense import embed_font

    output.mkdir(parents=True, exist_ok=replace)
    assets = output / "assets"
    assets.mkdir(exist_ok=replace)
    font, notice = embed_font(html, assets / "noto-sans-sc-subset.woff")
    html = html.replace("__FONT__", font).replace(
        "__FONT_LICENSE__", notice.replace("</script", "<\\/script")
    )
    (output / "index.html").write_text(html, encoding="utf-8")
    manifest = {
        "dashboard_version": config.DASHBOARD_VERSION,
        "built_at": data["display"]["built_at"],
        "dataset": data["dataset"],
        "source_ads_sha256": data["display"]["ads_sha256"],
        "html_sha256": hashlib.sha256(html.encode()).hexdigest(),
        "privacy_minimum_people": data["privacy"]["minimum_people"],
        "source_files": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                Path(__file__),
                *(templates / f"dashboard.{ext}" for ext in ("html", "css", "js")),
            ]
        },
    }
    (output / "build_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "使用说明.md").write_text(
        "# 祈愿数据观测大屏\n\n"
        "双击 index.html 即可离线展示，单独复制该文件也可使用。\n\n"
        "- 点击卡池按钮或卡池构成条，联动规模、月度和五星观察。\n"
        "- 月份范围、快捷区间仅影响月度趋势；抑制格保留缺口，不补零、不回推。\n"
        "- 星期小时、账号分布与名称榜为全局聚合，不受卡池或月份筛选影响。\n"
        "- 名称搜索只在已发布的前12个原始名称内进行；按原始名称统计，不合并别名。\n"
        "- 五星观察可切换间隔分布与账号分组占比；全池视图默认展示角色活动池。\n"
        "- F切换全屏；P启动或暂停每8秒卡池轮播；R复位；Esc关闭说明与详情。\n"
        "- 图上悬停或键盘聚焦查看数值；点击趋势月份可固定该月解读。\n\n"
        "数据为DS03已发布受保护聚合，统计时间2020-12—2022-07，时区未知。"
        "历史留存样本存在自选择与缺失，不能推算官方概率、保底、活跃或消费。\n",
        encoding="utf-8",
    )
    return output


def serve(directory: Path, port: int = 8765) -> None:
    """只在本机服务交付目录，不把项目与数据库暴露给浏览器。"""
    root = config.PRESENTATION_DIR.resolve()
    directory = directory.resolve(strict=True)
    if not directory.is_relative_to(root) or not (directory / "index.html").is_file():
        raise ValueError("仅允许服务reports内已经构建的大屏。")

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            return

    handler = partial(QuietHandler, directory=str(directory))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Local: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="制作并展示离线祈愿数据大屏")
    parser.add_argument("--analysis", type=Path, help="已有受保护ADS图集目录")
    parser.add_argument("--output", type=Path, help="新的项目内交付目录")
    parser.add_argument("--replace", action="store_true", help="显式更新带大屏清单的已有目录")
    parser.add_argument("--serve", action="store_true", help="构建后启动本机预览")
    parser.add_argument("--existing", type=Path, help="仅服务已有reports交付目录，不重建")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        output = (
            args.existing
            if args.existing
            else build(args.analysis, args.output, replace=args.replace)
        )
        print(json.dumps({"dashboard": str(output)}, ensure_ascii=False), flush=True)
        if args.serve or args.existing:
            serve(output, args.port)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"大屏未完成：{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
