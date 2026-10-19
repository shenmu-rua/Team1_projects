"""只复用受保护ADS和聚合稽核，制作内嵌矢量图、字体与讲稿的离线HTML答辩。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from xml.etree import ElementTree as ET

from . import config
from .ads import MIN_PEOPLE, POOL_NAMES
from .speech import compose, glossary_markdown


def without_scope(text: str) -> str:
    """仅移除Q01独立章节，保留分析正文和后续复现说明。"""
    return "".join(
        part
        for part in re.split(r"(?=^#{2,3} )", text, flags=re.M)
        if not re.search(r"\]\(Q01_[^)]+\)", part)
    )


def table(headers, rows, widths=None):
    cols = (
        ""
        if widths is None
        else "<colgroup>"
        + "".join(f'<col style="width:{width}%">' for width in widths)
        + "</colgroup>"
    )
    return (
        "<table>"
        + cols
        + "<thead><tr>"
        + "".join(f"<th>{x}</th>" for x in headers)
        + (
            "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{x}</td>" for x in row) + "</tr>" for row in rows)
            + "</tbody></table>"
        )
    )


def rows(items):
    return (
        '<div class="rows">'
        + "".join(
            f'<div class="row"><div class="label">{label}</div><p>{text}</p></div>'
            for label, text in items
        )
        + "</div>"
    )


def make_slides(data: dict, audit: dict, manifest: dict) -> list[dict]:
    """演示正文与讲稿；所有真实数字取自聚合，流程页不伪造记录示例。"""
    slides = []
    metrics, scope = audit["metrics"], data["scope"]
    pools = {row["pool_group"]: row for row in data["pools"]}
    role = pools[301]
    role_share = 100 * role["pulls"] / scope["pulls"]
    role_rate = 100 * role["star5"] / role["pulls"]
    rate_groups = [row for row in data["rates"] if row["pool_group"] == 301]
    peak_month = max(
        (row for row in data["months"] if row["pulls"] is not None), key=lambda row: row["pulls"]
    )
    peak_hour = max(
        (row for row in data["clock"] if row["pulls"] is not None), key=lambda row: row["pulls"]
    )
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    cdf1000 = (
        100
        * sum(row["counts"][0] for row in data["volume_bins"] if row["hi"] and row["hi"] <= 1000)
        / scope["people"]
    )
    top = data["items"][0]
    top_share = (
        100
        * sum(row["pulls"] for row in data["items"])
        / sum(row["star5"] for row in data["pools"])
    )
    gap_totals = {
        pool: sum(row["counts"][pool] for row in bins) for pool, bins in data["gap_bins"].items()
    }
    gap_peaks = {
        pool: max(bins, key=lambda row: row["counts"][pool])
        for pool, bins in data["gap_bins"].items()
    }
    role_high = max(rate_groups, key=lambda row: row["quartile"])
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y年%m月%d日")

    def add(
        title,
        body,
        notes,
        section,
        source="docs/数据清洗.md；docs/图表制作.md",
        kind="text",
        chart=None,
    ):
        slides.append(
            dict(
                title=title,
                body=body,
                notes=notes,
                section=section,
                source=source,
                kind=kind,
                chart=chart,
            )
        )

    add(
        "原神抽卡记录清洗与可视化分析",
        '<h1>原神抽卡记录<br>清洗与可视化分析</h1><p class="lead">项目汇报与答辩</p>'
        '<p class="cover-note">抽卡记录经过哪些处理，图中的数字如何得到，结论能够说明什么？</p>'
        f'<p class="cover-date">{today}</p>',
        "本项目围绕抽卡记录建立一套可复现的清洗、汇总和图表流程。汇报先解释数据如何进入可信的分析层，"
        "再说明图表主题与统计口径，最后逐图解读。重点是让图中的数字有清楚的计算来源，并明确记录完整性对解释的影响。",
        "项目介绍",
        kind="cover",
    )

    add(
        "研究问题与交付目标",
        '<p class="lead">围绕留存抽卡记录，回答结构、时间和分布问题</p>'
        + rows(
            [
                ("记录结构", "不同卡池的记录量与记录内五星占比如何分布？"),
                ("时间特征", "记录集中在哪些月份、星期和小时？"),
                ("账号分布", "账号留存抽数、分组五星占比和相邻五星间隔有哪些特征？"),
                ("交付内容", "独立清洗库、受保护ADS、七张分析图，以及本地可复现的制作入口。"),
            ]
        )
        + f'<p class="small muted">主分析采用03口径：{scope["people"]:,}个账号、{scope["pulls"]:,}抽；'
        f"{scope['first_time'][:10]}—{scope['last_time'][:10]}，时区未知。</p>",
        "问题分成记录结构、时间特征和账号分布。七张分析图分别对应这些问题。主分析范围在这里作为统计口径说明，"
        "不做来源规模对比。账号数在来源内去重，公开记录是自选择和留存后的样本，因此所有发现都以这些记录为对象。",
        "项目介绍",
    )

    add(
        "项目流程与数仓分层",
        table(
            ["层次", "处理职责", "主要产物"],
            [
                ("原始层 / ODS", "只读既有导入库，保留原始依据", "pulls及必要维表"),
                (
                    "DWD + DIM",
                    "校验、标准化、去重、冲突隔离、池内排序",
                    "dwd_pull、维表、拒绝原因表",
                ),
                ("DWS", "按账号池、日期、卡池、物品身份汇总", "四张可对账的汇总表"),
                ("ADS", "形成图表口径，实施小样本与互补抑制", "只包含可发布聚合的ads.json"),
                ("表达与交付", "蓝粉主题出图、解释结论、记录复现信息", "分析报告、图集、HTML答辩"),
            ],
            [18, 45, 37],
        ),
        "分层的目的在于区分原始依据、清洗明细、复用汇总与面向图表的发布结果。ODS在此指既有原始库，"
        "不意味着本次重命名或复制源表。DWD/DWS仍有内部账号粒度，不能直接对外展示；只有经过ADS保护的结果进入图表和汇报。",
        "项目流程",
        "src/genshin_insight/pipeline.py；dwd.py；dws.py；ads.py",
    )

    add(
        "清洗处理链",
        '<div class="milestones">'
        + "".join(
            f'<div class="milestone"><span class="step">{i:02}</span><div><h2>{title}</h2><p>{desc}</p></div></div>'
            for i, (title, desc) in enumerate(
                [
                    ("建立只读边界", "限制源表与源列；新结果写入项目内独立临时库。"),
                    ("验证关联与字段", "检查账号、来源、物品、卡池关联和基础值是否合法。"),
                    ("标准化与去重", "统一时间文本；重复保留一条，冲突全部隔离。"),
                    ("重建顺序与汇总", "池内重建连续序号；重算DWS，记录待复核标记。"),
                    ("稽核与完整性检查", "检查总量、去向、序号、星级、外键和SQLite完整性。"),
                    ("发布清洗产物", "检查全部通过后发布独立新库与聚合报告。"),
                ],
                1,
            )
        )
        + "</div>",
        "清洗在独立临时产物中完成，原库始终保持只读。处理步骤依次是建立边界、验证、标准化和去重、重建顺序、稽核、发布。"
        "规则在本地程序执行，异常使用固定原因代码记录。任一关键检查失败就停止发布，使不完整的临时结果不会被当作正式清洗库使用。",
        "项目流程",
        "src/genshin_insight/pipeline.py；db.py；quality.py",
    )

    add(
        "基础校验与标准化",
        table(
            ["字段或关系", "实现方法", "处理依据"],
            [
                ("维表关联", "来源归属、账号、物品、卡池必须一致", "不能关联或归属冲突时隔离"),
                ("时间", "校验真实日历，统一秒级无时区文本", "保留时区未知；不猜测日期范围"),
                (
                    "名称与星级",
                    "去首尾空白；校验非空名称与合法星级",
                    "保留多语言原名，类型语义另行复核",
                ),
                ("业务ID", "数字文本保持TEXT，按精确数字顺序比较", "不转浮点，避免长数字精度损失"),
            ],
            [20, 43, 37],
        )
        + '<p class="takeaway">能确认的格式差异直接标准化；无法确认的业务语义保留标记。</p>',
        "标准化的范围是能够确定的格式问题。时间会验证真实日历并统一文本形式，但不补造时区。名称仅去首尾空白，"
        "不会把不同语言写法自动当成同一实体。业务ID保持文本存储，用精确的数字顺序比较，避免浮点转换使长ID失真。",
        "实现方法",
        "docs/数据清洗.md；src/genshin_insight/dwd.py；dims.py",
    )

    add(
        "去重与冲突隔离",
        rows(
            [
                ("第一层", "按 <code>(source_file_id, source_row)</code> 检查相同来源位置。"),
                ("第二层", "按 <code>(player_id, gacha_id)</code> 检查账号内相同业务ID。"),
                (
                    "相同内容",
                    "保留最小原记录键，其余登记为重复；本次移除重复记录"
                    f"<strong>{metrics['duplicate_rows_removed']:,}条</strong>。",
                ),
                ("内容冲突", "候选记录全部隔离，不任意挑选；无ID记录保留合法的同秒同物品组合。"),
            ]
        )
        + '<p class="small muted">同秒同物品可能来自十连，不能仅凭时间、物品和卡池判重。</p>',
        "去重分两层，先识别相同来源位置，再识别同一账号的业务ID。如果两条内容相同则保留一条；如果内容冲突则全部隔离。"
        "没有ID时不使用时间、物品、卡池的组合强行去重，因为十连可能自然出现相同组合。"
        f"本次实际移除{metrics['duplicate_rows_removed']:,}条重复记录，具体原因见清洗聚合报告。",
        "实现方法",
        "docs/数据清洗.md；src/genshin_insight/dwd.py",
    )

    add(
        "同秒排序与类型复核",
        '<div class="columns"><div><h2>池内顺序</h2>'
        "<p>按标准时间、ID可用性、精确数字ID及稳定来源位置排序，重新生成连续 <code>pool_seq</code>。</p>"
        f'<p class="big-label">清洗全体记录中，<strong>{metrics["ambiguous_same_second_pulls"]:,}抽</strong>带有同秒顺序歧义标记。</p>'
        "</div><div><h2>类型语义</h2>"
        f"<p>发现<strong>{metrics['item_type_review_sources']}个来源</strong>需复核类型编码，涉及"
        f"<strong>{metrics['item_type_review_pulls']:,}抽</strong>。</p>"
        "<p>保留记录并标记，不翻转类型编码；分析优先使用已校验的星级、卡池与时间。</p></div></div>"
        '<p class="takeaway">五星间隔计算只使用排序明确的账号池组合。</p>',
        "同秒排序和类型复核是不同的问题。缺失ID的同秒多条记录只能形成稳定顺序，不能断言真实秒内先后，因此加歧义标记。"
        "类型编码可能因来源不同而含义不一致，记录不会被直接删除或反转类型。这里的数量来自清洗全体记录的稽核，"
        "与主分析03口径应分别理解；后续间隔图只使用主分析内排序明确的账号池。",
        "实现方法",
        "docs/数据清洗.md；清洗聚合报告metrics",
    )

    add(
        "清洗结果与发布门槛",
        '<div class="equation">'
        + f"{metrics['input_pulls']:,} = <em>{metrics['kept_pulls']:,}</em> + {metrics['rejected_pulls']:,}"
        '</div><p class="lead">输入记录数 = 保留记录数 + 移除或隔离记录数（清洗全体口径）</p>'
        + rows(
            [
                ("数量守恒", "每条输入只有一个去向；保留、拒绝互不重叠。"),
                ("顺序与汇总", "池内序号连续，四张DWS总量与DWD一致，星级数量能够对账。"),
                ("完整性", "外键检查、SQLite完整性检查通过后才发布。"),
            ]
        )
        + f'<p class="takeaway">本次清洗的{len(audit["checks"])}项稽核全部通过；实际冲突隔离{metrics["conflicting_rows_quarantined"]:,}条。</p>',
        f"这个等式是最基本的数量守恒。输入{metrics['input_pulls']:,}条，保留{metrics['kept_pulls']:,}条，"
        f"移除或隔离{metrics['rejected_pulls']:,}条。保留与拒绝的集合不重叠，"
        f"所有输入进入暂存，四张汇总表与清洗明细总量一致。{len(audit['checks'])}项检查包括序号、星级、外键和SQLite完整性。"
        "这些检查证明产物按规则自洽，不等于证明原始留存记录完整或样本代表全部玩家。",
        "实现方法",
        "清洗聚合报告checks；src/genshin_insight/quality.py；pipeline.py",
    )

    add(
        "DWS聚合与ADS发布",
        table(
            ["复用汇总", "统计粒度", "用于哪些分析"],
            [
                ("dws_player_pool", "来源内账号 × 合并卡池", "卡池结构、账号记录量、分组五星占比"),
                ("dws_daily", "日期 × 原卡池 × 星级", "卡池月度记录"),
                ("dws_item", "原卡池 × 原物品身份", "五星原始名称记录榜"),
                ("DWD必要列", "内部池内序号与时间", "星期小时矩阵、相邻五星序号差"),
            ],
            [26, 33, 41],
        )
        + '<p class="takeaway">ADS负责统一分母、保护小样本，并向图表提供稳定的应用口径。</p>',
        "DWS解决反复计算相同汇总的问题。账号池表用于记录量和分组率，日汇总用于月度趋势，物品汇总用于名称榜。"
        "星期小时需要时间字段，五星间隔需要序号与星级，因此由本地程序处理必要明细列后只返回聚合。"
        "DWS中的账号粒度不会直接进入演示，发布前还要经过ADS的小样本保护。",
        "实现方法",
        "src/genshin_insight/dws.py；ads.py",
    )

    add(
        "小样本保护与互补抑制",
        rows(
            [
                (
                    "发布门槛",
                    f"贡献账号不足<strong>{MIN_PEOPLE}个</strong>的格子，指标和贡献人数同时置空。",
                ),
                (
                    "互补抑制",
                    "若一个可加分区只隐藏一格，再隐藏另一格，防止通过总量减去其余值反推。",
                ),
                ("尾部合箱", "分布合并相邻稀疏箱；累计占比只在安全分箱上计算。"),
                (
                    "贡献人数",
                    "跨日或跨物品的已有去重人数取最大值作为保守下界；确认互斥的账号分箱才允许相加。",
                ),
            ]
        ),
        "保护在ADS发生，图表拿到的就是空值，不能仅在图片上遮挡原数。互补抑制解决单个隐藏格可由总量减法反推的问题。"
        "贡献人数不能随便相加，同一账号可能跨天、卡池编码和物品身份重复出现，因此使用已有格内人数最大值作为保守下界。"
        "这会多隐藏一些实际人数足够的格子，但能避免把重叠人数误当独立贡献人数。",
        "实现方法",
        "src/genshin_insight/ads.py：suppress、coarsen",
    )

    add(
        "本地实现与复现方式",
        '<div class="columns wide-left"><div><h2>短入口复用完整流程</h2>'
        "<pre>from genshin_insight.charts import generate\n\noutput = generate()</pre>"
        "<p>SQLite执行筛选、聚合与窗口计算；Pandas分组，NumPy计算分位数；Matplotlib绘制蓝粉图表。</p>"
        "</div><div><h2>模块按职责拆分</h2>"
        + rows(
            [
                ("ads.py", "聚合、分箱和小样本保护"),
                ("viz/", "主题接入、绘图与自检"),
                ("charts.py", "图集运行与复现清单"),
            ]
        )
        + '</div></div><p class="small muted">路径使用pathlib；连接使用上下文管理器；项目代码不导入os；import时不连接数据库或加载绘图。</p>',
        "入口保持简短，计算和绘图通过本地import复用。SQLite适合在本地执行大规模分组与窗口函数；Pandas用于账号抽数分组，"
        "NumPy提供分位数计算，Matplotlib统一主题。模块导入不触发真实数据读取或绘图副作用，所有处理由显式函数调用开始。"
        "HTML制作进一步复用已经发布的ADS和图表函数，因此不需要重新读取数据库明细。",
        "实现方法",
        "make_charts.py；src/genshin_insight/{ads,charts,config}.py；viz/",
    )

    add(
        "蓝粉主题与颜色语义",
        '<div class="palette">'
        + "".join(
            f'<div class="swatch"><div class="color-chip" style="--swatch:var(--{color})"></div><div><strong>{name}</strong><span>{meaning}</span></div></div>'
            for color, name, meaning in [
                ("panel", "冷蓝地面", "背景与结构：承托数据、减少视觉竞争"),
                ("pink", "藕粉主色", "角色活动池与需要关注的主要数据"),
                ("blue", "烟蓝对比", "常驻祈愿；同一对象跨图保持同色"),
                ("navy", "深蓝系列", "武器活动祈愿"),
                ("violet", "雾紫桥色", "新手祈愿；协调冷蓝与藕粉"),
                ("gray", "中性灰", "背景对象或受抑制格；红色仅用于警示"),
            ]
        )
        + '</div><p class="small muted">字体：Noto Sans SC / 思源黑体；连续数值使用浅粉→深粉的单色渐变。</p>',
        "蓝粉主题的核心是冷蓝地面与藕粉数据。卡池映射固定：角色粉、常驻蓝、武器深蓝、新手紫，避免换图后同一个颜色变换含义。"
        "热力图是连续数值，不把不同色相当作数值刻度，而使用单粉渐变。字体只使用开源中文字体。HTML还把用到的字体子集内嵌，便于离线汇报。",
        "图表主题",
        "theme/SKILL.md；theme/theme.py；docs/项目初始化.md",
    )

    add(
        "图形选择与视觉约束",
        table(
            ["统计问题", "采用图形", "阅读理由"],
            [
                ("规模与占比", "横向条形 + 独立面板", "从零比较长度；不同量纲分别展示"),
                ("月度变化", "四个卡池的小多折线", "保留时间顺序；明确各池独立纵轴"),
                ("星期 × 小时", "热力矩阵 + 格内数字", "定位组合高值；对数色阶标实际数值"),
                ("分布与组间差异", "分箱分布、累计占比、分位区间", "同时展示集中位置与离散程度"),
                ("名称排行", "排序横条与直接标注", "以计数解释记录频次"),
            ],
            [23, 35, 42],
        )
        + '<p class="small muted">禁止双Y轴、3D、饼图/环形图与彩虹色阶；横条基线为0；刻度不小于8磅。</p>',
        "先确定问题，再决定图形。卡池抽数和五星占比量纲不同，采用独立面板，不把两条纵轴放在同一坐标区。"
        "月度用折线保留时间顺序，星期与小时用矩阵定位组合高值。分布图兼顾位置与离散程度，避免只报告均值。"
        "这些选择遵守项目图表规范，并让读者能从图形直接核对数量。",
        "图表主题",
        "docs/图表规范.md；theme/SKILL.md",
    )

    add(
        "一张图的阅读顺序",
        rows(
            [
                ("结论标题", "包含由代码计算的关键数字，长度不超过40字。"),
                ("口径与限制", "先确认对象、时间、分母、分组方式和记录完整性。"),
                ("坐标与图元", "核对单位、零基线、独立坐标尺度与对数色阶。"),
                ("直接标注", "在图元旁读取数值；类目放在坐标区内部。"),
                ("来源与版本", "检查数据来源、制作入口、配置哈希与清洗规则版本。"),
            ]
        )
        + '<p class="small muted">图集规格：16:9、200 dpi；16英寸宽基准下标题22pt、刻度11.5pt、来源9.5pt。</p>',
        "阅读图表时先看标题，但判断结论要以副标题里的口径为前提。然后确认坐标单位与尺度，尤其是月度小多图的独立纵轴、"
        "热力图的对数颜色以及分布尾部的开放箱。直接标注帮助核对数字，来源行用于追溯脚本和配置。"
        "接下来的七张图都按这个顺序解释。",
        "图表主题",
        "theme/SKILL.md；src/genshin_insight/viz/__init__.py",
    )

    by_name = {
        figure["file"][:3]: figure
        for figure in manifest["figures"]
        if figure["file"].startswith("A")
    }

    def chart(code, notes):
        figure = by_name[code]
        add(
            figure["title"],
            "",
            notes,
            "分析结果",
            f"{figure['file']}；受保护ADS；viz/plots.py",
            "chart",
            code,
        )

    chart(
        "A01",
        "先读左侧抽数，再读右侧记录内五星占比。两边采用相同卡池顺序与颜色，却使用不同单位的独立坐标轴。"
        "角色活动池贡献约三分之二的抽数。右侧的分母是该卡池的全部留存抽数，属于抽数加权的总体记录比率，不能解释为每个账号的典型值。",
    )
    add(
        "卡池构成：抽数与记录内占比",
        f'<p class="lead">角色活动祈愿贡献{role_share:.1f}%的记录；记录内五星占比为{role_rate:.2f}%</p>'
        + table(
            ["卡池", "留存抽数", "五星记录", "记录内五星占比"],
            [
                (
                    POOL_NAMES[pool],
                    f"{pools[pool]['pulls']:,}",
                    f"{pools[pool]['star5']:,}",
                    f"{100 * pools[pool]['star5'] / pools[pool]['pulls']:.2f}%",
                )
                for pool in (301, 302, 200, 100)
            ],
            [29, 25, 23, 23],
        )
        + '<p class="takeaway">占比＝该池五星记录数 ÷ 该池抽数；301与400合并到角色活动池。</p>'
        + '<p class="small muted">来源选择、历史缺失和不同账号记录量会影响总体比率；不作为官方概率估计。</p>',
        "这张表给出横条对应的计数。总体记录内五星占比用五星记录总数除以抽数总量，因此抽数较多的账号具有更大权重。"
        "后面的分组图则先计算每个账号的占比，再展示组内中位数，两者回答的问题不同。角色双池保留原始编码，在应用口径上合并。",
        "分析结果",
        "ADS.pools；src/genshin_insight/ads.py",
    )

    chart(
        "A02",
        "四个面板分别是新手、常驻、角色活动和武器活动池。"
        f"峰值来自{POOL_NAMES[peak_month['pool_group']]}{peak_month['month']}，约{peak_month['pulls'] / 10000:.1f}万抽。"
        "各面板纵轴范围不同，比较卡池绝对规模时要读数值，不比较折线在面板中的高度。起止月可能不完整，受抑制或缺失月份没有插值。",
    )
    add(
        "月度变化：峰值来自留存记录",
        '<div class="columns"><div>'
        f'<div class="big">{peak_month["pulls"] / 10000:,.1f}<small>万抽</small></div>'
        f'<div class="big-label">{escape(peak_month["month"])} · {POOL_NAMES[peak_month["pool_group"]]}<br>可发布月份中的单池最高值</div>'
        '<p class="muted">按记录时间的自然月汇总，未按覆盖天数或账号规模标准化。</p></div><div>'
        + rows(
            [
                ("读什么", "单个卡池随时间变化的留存抽数，以及峰值月份。"),
                ("怎么比", "各池独立纵轴；跨池比较时读取万抽数值。"),
                (
                    "解释边界",
                    "记录集中可能同时受采集和留存影响；不能单凭峰值归因于版本或活跃变化。",
                ),
            ]
        )
        + "</div></div>",
        "月度图适合定位后续核查的时间段。峰值月说明在这批留存记录中抽数最多，并不直接衡量当月玩家人数或活跃。"
        "如果要研究版本影响，需要额外的版本日历、稳定采样或曝光基数，并且确认时区。当前没有这些证据，因此只报告描述性峰值。",
        "分析结果",
        "ADS.months；viz/plots.py：months",
    )

    chart(
        "A03",
        "横轴为0至23时，纵轴为星期，单格为所有对应星期与小时的累计万抽。周二18时最大。"
        "颜色采用对数刻度，因为格子间跨越两个数量级；颜色相近不表示抽数差距相同，准确数值应读取格内数字。时间按无时区文本直接解析。",
    )
    add(
        "时段分布：累计时间组合的高值",
        '<div class="columns"><div>'
        f'<div class="big">{weekdays[peak_hour["weekday"]]}{peak_hour["hour"]}<small>时</small></div>'
        f'<div class="big-label">累计{peak_hour["pulls"] / 10000:.1f}万抽<br>占主分析记录的{100 * peak_hour["pulls"] / scope["pulls"]:.1f}%</div>'
        '<p class="muted">这是跨多周累积的星期×小时组合，不是单日某一小时的抽数。</p></div><div>'
        + rows(
            [
                ("数值", "每格为万抽；颜色表示从低到高的累计数量。"),
                ("色阶", "对数颜色展开低值差异；色条直接标实际抽数单位。"),
                ("限制", "时区未知，没有星期曝光天数或在线人数作分母；不能解释为在线高峰。"),
            ]
        )
        + "</div></div>",
        "时段矩阵把日期压缩成星期和小时，能够指出留存记录集中的组合。周二18时的占比以主分析全部抽数为分母。"
        "每个星期在记录期中出现的天数、各天留存账号数可能不同，所以当前不做日均强度比较。对数色阶只是改善跨数量级的显示，不改变格内实际数值。",
        "分析结果",
        "ADS.clock；viz/plots.py：clock",
    )

    chart(
        "A04",
        "左侧显示每个抽数分箱包含的账号占比，右侧在分箱上界读取累计占比。"
        f"中位数{data['volume_median']:,.0f}抽来自本地账号总量，"
        "不是对分箱曲线插值得到。最后一个箱为5001抽及以上，没有有限上界；累计图末点标作全部。抽数是留存记录量，不能换算付费。",
    )
    add(
        "账号记录量：中位数与累计分布",
        '<div class="columns"><div>'
        f'<div class="big">{data["volume_median"]:,.0f}<small>抽</small></div>'
        f'<div class="big-label">每账号留存抽数中位数<br>{cdf1000:.1f}%的账号留存记录不超过1,000抽</div>'
        "<p>账号内合并所有卡池，每个账号在分布中计一次。</p></div><div>"
        + rows(
            [
                ("分箱图", "看账号集中在哪个记录量区间，以及尾部占比。"),
                ("累计图", "在箱上界读取累计占比；连线不提供箱内分布。"),
                ("中位数", "由本地账号汇总计算，避免仅用平均数概括偏斜分布。"),
            ]
        )
        + "</div></div>",
        "先在每个账号内部把所有卡池抽数相加，再形成账号记录量分布。账号分箱互斥，所以箱内账号数可以安全相加。"
        f"{data['volume_median']:,.0f}抽是账号总量的中位数，{cdf1000:.1f}%的账号在1,000抽以内。"
        "右图是分箱累计结果，不是完整经验累计分布曲线，不能从两个箱之间的直线推断某个任意抽数的精确比例。",
        "分析结果",
        "ADS.volume_bins；ADS.volume_median",
    )

    chart(
        "A05",
        "四个面板共享纵轴。各池独立按账号抽数四分组，点是账号五星占比的组内中位数，线是25%至75%分位区间。"
        "新手池因抽数取值集中合并成全部账号，明确标为分组退化。"
        f"角色池高记录量组中位数约{role_high['median']:.2f}%，组间的区间不能作为置信区间解释。",
    )
    add(
        "分组五星占比：账号等权的分布",
        '<p class="formula">每账号五星占比 = 五星记录数 ÷ 留存抽数</p>'
        + table(
            ["角色池抽数分组", "账号数", "中位数", "25%—75%分位区间"],
            [
                (
                    f"Q{row['quartile']}"
                    + (
                        " 低记录量"
                        if row["quartile"] == 1
                        else " 高记录量"
                        if row["quartile"] == 4
                        else ""
                    ),
                    f"{row['people']:,}",
                    f"{row['median']:.2f}%",
                    f"{row['q25']:.2f}%—{row['q75']:.2f}%",
                )
                for row in rate_groups
            ],
            [29, 19, 18, 34],
        )
        + '<p class="small muted">每账号等权，零五星账号保留；重复分组边界会合并。区间描述账号分布，不是置信区间；记录量不等于付费。</p>',
        "总体比率把全部抽数加起来做分母；这里则每个账号先得到一个比率，再计算中位数和四分位区间，所以账号等权。"
        "零五星账号没有被排除。角色池各组中位数接近，较高记录量组的四分位区间更窄，但分组基于留存抽数，"
        "选择与缺失机制尚不明确，不能把这些差异解释为投入导致概率变化。",
        "分析结果",
        "ADS.rates；ads.py：pd.qcut、np.percentile",
    )

    chart(
        "A06",
        "每个卡池只保留排序明确、相邻已记录五星之间已闭合的区间。"
        f"角色池最高占比箱约占{100 * gap_peaks[301]['counts'][301] / gap_totals[301]:.1f}%，"
        f"武器池最高占比箱约占{100 * gap_peaks[302]['counts'][302] / gap_totals[302]:.1f}%。"
        "每个卡池分别合并尾部稀疏箱，所以角色与常驻尾箱是81抽及以上，武器尾箱是71抽及以上。三列横轴百分比尺度一致。",
    )
    gap_rows = []
    for pool in (200, 301, 302):
        bins = data["gap_bins"][pool]
        count = sum(row["counts"][pool] for row in bins)
        peak = max(bins, key=lambda row: row["counts"][pool])
        label = f"{peak['lo']}—{peak['hi']}抽" if peak["hi"] else f"{peak['lo']}抽及以上"
        gap_rows.append(
            (POOL_NAMES[pool], f"{count:,}段", label, f"{100 * peak['counts'][pool] / count:.1f}%")
        )
    add(
        "五星间隔：已闭合区间的分箱分布",
        '<p class="formula">间隔 = 本次已记录五星的pool_seq − 上次已记录五星的pool_seq</p>'
        + table(["卡池", "已闭合区间", "占比最高的箱", "该箱占比"], gap_rows, [29, 25, 27, 19])
        + '<p class="takeaway">“半数不超过80抽”来自累计分箱上界，不能把80抽写成精确中位数。</p>'
        + '<p class="small muted">首个五星前段、未闭合尾段排除；排序歧义账号池排除；历史缺失仍无法识别，因此不推断真实保底。</p>',
        "LAG窗口函数在账号和卡池内按序号找上次五星，再计算差。首个观察到的五星没有上一次五星，不能构成闭合区间。"
        "最后一次五星之后的记录同样没有闭合终点。本图描述已观察且闭合的区间，短区间和长区间的被观察机会可能不同。"
        "标题只表示累计分箱在80抽内已经超过一半，精确中位数位于该箱内部，当前没有将箱上界当作中位数。",
        "分析结果",
        "ADS.gap_bins；ads.py：LAG(pool_seq) OVER (...)",
    )

    chart(
        "A07",
        f"原始名称按五星记录次数降序排列，主粉强调榜首，其余灰色。前{len(data['items'])}个原始名称覆盖约{top_share:.1f}%的五星记录。"
        "相同原始名称合并，不同语言名称不自动归一；角色与武器都可以进入榜单。次数可以包含同一账号重复抽中，因此不能直接读作独立拥有人数。",
    )
    add(
        "名称榜：记录频次与名称口径",
        '<div class="columns"><div>'
        f'<div class="big">{top["pulls"]:,}<small>次</small></div>'
        f'<div class="big-label">{escape(top["name"])} · 当前原始名称榜首<br>前{len(data["items"])}个名称覆盖五星记录的{top_share:.1f}%</div>'
        '<p class="muted">频次是五星记录次数；同一账号可以贡献多次记录。</p></div><div>'
        + rows(
            [
                ("名称", "只合并精确原始名称，翻译别名保留分离。"),
                ("筛选", "按已校验星级筛选，不依赖待复核的物品类型编码。"),
                ("解释", "名称曝光机会和留存历史不同；不能直接据此排名角色人气。"),
            ]
        )
        + "</div></div>",
        f"榜首{top['name']}{top['pulls']:,}次，这是记录频次，不是独立账号数。"
        "多语言名称尚未建立可信映射，直接合并可能引入错误，"
        "所以保留原名。榜单也受不同物品在记录窗口内的曝光机会、账号选择和历史缺失影响。如果要做人气分析，"
        "需要先统一实体，并定义可比的曝光与选择口径。",
        "分析结果",
        "ADS.items；ADS.pools；dim_item.rank_type",
    )

    add(
        "主要结论与解释边界",
        table(
            ["已经得到的描述", "解释边界", "进一步研究所需证据"],
            [
                (
                    f"角色活动池占留存抽数{role_share:.1f}%",
                    "是记录构成，不能直接换算市场或消费份额",
                    "稳定的采样与完整历史",
                ),
                (
                    "月度和星期小时有明显高值",
                    "不能仅凭时间对应关系解释为版本因果效应",
                    "确认时区、曝光基数与事件日历",
                ),
                (
                    f"账号留存抽数中位数{data['volume_median']:,.0f}抽",
                    "不等于完整游戏历史或付费水平",
                    "账号记录覆盖与投入信息",
                ),
                (
                    "已闭合五星间隔呈集中分布",
                    "缺失与删失未解决，不作为官方保底推断",
                    "完整连续历史与明确的观察设计",
                ),
            ],
            [35, 37, 28],
        ),
        "结论和证据边界要一起汇报。当前可以确认样本内的记录构成、时间集中和分布特征。进一步的玩家行为、投入或机制研究，"
        "需要额外口径与数据支持。项目价值是建立可追溯的处理和表达流程，使后续补充证据时能够沿同一套规则复算，而不是把描述性图形包装成因果结论。",
        "结论与答辩",
    )

    add(
        "答辩常见问题",
        rows(
            [
                (
                    "为何分面",
                    "抽数与五星占比量纲不同；独立面板能保留真实刻度，避免双Y轴制造视觉交点。",
                ),
                ("如何去重", "先来源位置、再账号内业务ID；相同内容保留一条，内容冲突全部隔离。"),
                ("能否算保底", "当前只有留存记录；首末段与缺失历史限制了真实间隔的识别。"),
                (
                    "如何复现",
                    "只读源库、独立清洗产物、固定口径与配置哈希；本地import串联处理和出图。",
                ),
            ]
        ),
        "答辩可按四个问题展开：分面解决不同量纲下的阅读偏差；两层去重保证规则明确；间隔图受到观察历史限制，"
        "不能给出真实保底结论；复现依靠版本、参数、输入文件元信息与代码哈希。对尚未确认的类型和名称映射，"
        "保持待复核状态，并说明需要补充什么证据。",
        "结论与答辩",
    )

    add(
        "复现入口与后续完善",
        '<div class="columns wide-left"><div><h2>在项目目录显式运行</h2>'
        "<pre>python -m genshin_insight clean\npython make_charts.py\npython make_defense.py</pre>"
        '<p class="small muted">未安装包时先设置PYTHONPATH=src;.；清洗与图集生成新目录，HTML从既有ADS和聚合稽核制作。</p>'
        "</div><div><h2>后续工作</h2>"
        + rows(
            [
                ("语义", "复核物品类型，建立可追溯的多语言实体映射。"),
                ("时间", "确认时区、记录覆盖与曝光口径。"),
                ("分析", "在连续历史与观察机制明确后，再讨论更强的机制推断。"),
            ]
        )
        + "</div></div>",
        "三个入口对应清洗、制图和汇报。已经有清洗结果和ADS时，可以直接制作汇报，不必再次运行耗时清洗。"
        "每次图集保留配置、环境与输入元信息，HTML另外记录构建来源。下一步优先处理语义映射和时间覆盖问题，"
        "这些证据决定后续可以提出多强的分析结论。",
        "结论与答辩",
        "README.md；make_charts.py；make_defense.py；manifest.json",
    )

    add(
        "THANKS",
        "<h1>THANKS</h1>",
        "以上就是我的完整汇报。感谢各位老师的聆听，谢谢。",
        "结论与答辩",
        kind="closing",
    )
    speeches = compose(data, audit)
    if len(speeches) != len(slides):
        raise ValueError("逐页讲稿与PPT页数不一致。")
    for slide, speech in zip(slides, speeches, strict=True):
        slide["notes"] = speech
    return slides


def load_release(analysis: Path):
    """只读取发布聚合JSON；不连接任何数据库。"""
    manifest = json.loads((analysis / "manifest.json").read_text(encoding="utf-8"))
    data = json.loads((analysis / "ads.json").read_text(encoding="utf-8"))
    if data["dataset"] != 3:
        raise ValueError("当前答辩模板适配主分析03，拒绝混用其他来源。")
    for row in data["volume_bins"]:
        for name in ("counts", "people"):
            row[name] = {int(key): value for key, value in row[name].items()}
    data["gap_bins"] = {int(pool): bins for pool, bins in data["gap_bins"].items()}
    for bins in data["gap_bins"].values():
        for row in bins:
            for name in ("counts", "people"):
                row[name] = {int(key): value for key, value in row[name].items()}
    for section in ("pools", "rates", "items"):
        if any(row.get("suppressed") or row["people"] < MIN_PEOPLE for row in data[section]):
            raise ValueError("当前演示需要完整且达到发布门槛的聚合；不展开隐藏格。")
    source_name = Path(manifest["source_file"])
    if source_name.name != manifest["source_file"]:
        raise ValueError("来源标识必须为清洗库文件名。")
    audit = json.loads(
        (config.DATA_DIR / source_name.with_suffix(".json")).read_text(encoding="utf-8")
    )
    if audit["status"] != "success" or not all(check["passed"] for check in audit["checks"]):
        raise ValueError("清洗聚合稽核未通过，停止制作。")
    return data, audit, manifest


def inline_svg(path: Path, prefix: str) -> str:
    """命名空间化图元ID，防止多张内嵌SVG互相引用剪裁区域。"""
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    for element in root.iter():
        for key, value in list(element.attrib.items()):
            if key == "id":
                value = prefix + value
            else:
                value = re.sub(r"url\(#([^)]+)\)", lambda match: f"url(#{prefix}{match[1]})", value)
                if key.endswith("href") and value.startswith("#"):
                    value = "#" + prefix + value[1:]
            element.set(key, value)
    root.set("role", "img")
    root.set("aria-label", path.stem)
    return ET.tostring(root, encoding="unicode")


def vectorize(fig):
    """热力矩阵导出为原生矢量格，保留数值文字、色板和对数映射。"""
    import numpy as np

    for ax in fig.axes:
        for collection in ax.collections:
            collection.set_rasterized(False)
            if getattr(ax, "_colorbar", None):
                collection.set_edgecolor("face")
                collection.set_linewidth(0.3)
        for image in list(ax.images):
            values = image.get_array()
            left, right, bottom, top = image.get_extent()
            ax.pcolormesh(
                np.linspace(left, right, values.shape[1] + 1),
                np.linspace(top, bottom, values.shape[0] + 1),
                values,
                cmap=image.cmap,
                norm=image.norm,
                shading="flat",
                edgecolors="none",
                antialiased=False,
                zorder=image.zorder,
            )
            image.remove()
    return fig


def embed_font(characters: str, output: Path) -> tuple[str, str]:
    """仅内嵌本演示所需的开源字体字形，WOFF无需联网或额外Brotli依赖。"""
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from matplotlib import font_manager

    source = font_manager.findfont(font_manager.FontProperties(family="Noto Sans SC"))
    font = TTFont(source)
    notice = (
        font["name"].getDebugName(0)
        + "\n\n"
        + (Path(__file__).with_name("viz") / "font_license.txt").read_text(encoding="utf-8")
    )
    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs += [13, 14]
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text=characters)
    subsetter.subset(font)
    font.flavor = "woff"
    font.save(output)
    font.close()
    (output.parent / "FONT_LICENSE.txt").write_text(notice, encoding="utf-8")
    return base64.b64encode(output.read_bytes()).decode("ascii"), notice


def build(
    analysis: Path | None = None, output: Path | None = None, *, replace: bool = False
) -> Path:
    """制作单文件HTML与配套讲稿；仅显式运行时读文件、应用主题。"""
    from . import viz
    from .viz.plots import PLOTS

    analysis = (
        Path(analysis)
        if analysis
        else max(
            (path.parent for path in config.IMAGE_DIR.glob("analysis_*/manifest.json")),
            key=lambda path: (path / "manifest.json").stat().st_mtime_ns,
            default=None,
        )
    )
    if analysis is None:
        raise FileNotFoundError("请先制作分析图集，生成ADS与清单。")
    analysis = analysis.resolve(strict=True)
    now = datetime.now(timezone(timedelta(hours=8)))
    output = Path(output or config.PRESENTATION_DIR / f"defense_{now:%Y%m%d_%H%M%S}").resolve()
    if not all(path.is_relative_to(config.PROJECT_ROOT.resolve()) for path in (analysis, output)):
        raise ValueError("输入聚合与演示产物必须位于本项目内部。")
    data, audit, manifest = load_release(analysis)
    slides = make_slides(data, audit, manifest)
    if (
        replace
        and output.exists()
        and not all((output / name).is_file() for name in ("index.html", "build_manifest.json"))
    ):
        raise ValueError("只允许更新具有构建清单的既有答辩目录。")
    output.mkdir(parents=True, exist_ok=replace)
    assets = output / "assets"
    assets.mkdir(exist_ok=replace)
    import matplotlib

    matplotlib.use("Agg")
    viz.apply_theme(16)
    theme = viz.load_theme()
    matplotlib.rcParams.update({"svg.fonttype": "none", "svg.hashsalt": "genshin-defense"})
    source = theme.source_line(
        "原神清洗抽卡记录·主分析03",
        "make_charts.py / make_defense.py",
        f"{manifest['settings']['version']}+{manifest['config_hash']} / 清洗{audit['rule_version']}",
    )
    charts = {}
    for filename, plot in PLOTS:
        if not filename.startswith("A"):
            continue
        path = viz.save(vectorize(plot(data, source)), assets / f"{filename}.svg", ppt=True)
        charts[filename[:3]] = inline_svg(path, filename[:3].lower() + "-")
    foot = f"原神清洗记录·主分析03；图表 {manifest['settings']['version']}+{manifest['config_hash']}；清洗规则 {audit['rule_version']}"
    sections, notes, toc, manuscript = (
        [],
        [],
        [],
        [
            "# 原神抽卡记录清洗与可视化分析 · 完整答辩讲稿",
            "",
            "按32页PPT顺序编排，逐页正文可直接朗读，段尾包含翻页过渡。依据行用于备查，不必朗读；文末附术语速查，不增加PPT页数。",
            "",
        ],
    )
    for i, slide in enumerate(slides, 1):
        title = escape(slide["title"])
        if slide["kind"] == "chart":
            body = (
                charts[slide["chart"]] + f'<span class="chart-page">{i:02} / {len(slides)}</span>'
            )
        else:
            body = "" if slide["kind"] in ("cover", "closing") else f"<h1>{title}</h1>"
            body += f'<div class="slide-content">{slide["body"]}</div>'
        classes = "slide" + (" chart-slide" if slide["kind"] == "chart" else f" {slide['kind']}")
        footer = (
            ""
            if slide["kind"] == "closing"
            else (
                f"<footer><span>{escape(foot)}</span><span>{i:02} / {len(slides)}</span></footer>"
            )
        )
        sections.append(
            f'<section class="{classes}" id="slide-{i}" data-title="{title}" data-section="{slide["section"]}" aria-label="{i}. {title}">'
            f"{body}{footer}</section>"
        )
        notes.append(
            f'<template id="note-{i}"><p>{escape(slide["notes"])}</p><p class="notes-source">依据：{escape(slide["source"])}</p></template>'
        )
        toc.append(
            f'<li><button type="button" data-go="{i - 1}"><span class="toc-number">{i:02}</span><span>{title}</span></button></li>'
        )
        manuscript += [
            f"## {i:02} · {slide['title']}",
            "",
            slide["notes"],
            "",
            f"依据：{slide['source']}",
            "",
        ]
    manuscript += [glossary_markdown()]
    colors = {
        "bg": theme.BG,
        "panel": theme.PANEL,
        "ink": theme.INK,
        "ink-soft": theme.INK_SOFT,
        "muted": theme.MUTED,
        "faint": theme.FAINT,
        "axis": theme.AXIS,
        "pink": theme.MAIN,
        "blue": theme.PAST,
        "navy": theme.BLUE_700,
        "violet": theme.BRIDGE,
        "gray": theme.GRAY,
    }
    palette = ";".join(f"--{name}:{value}" for name, value in colors.items())
    template_path = Path(__file__).with_name("viz") / "defense.html"
    html = template_path.read_text(encoding="utf-8")
    for key, value in {
        "PALETTE": palette,
        "SLIDES": "\n".join(sections),
        "TOC": "".join(toc),
        "NOTES": "\n".join(notes),
    }.items():
        html = html.replace(f"__{key}__", value)
    font_data, notice = embed_font(html, assets / "noto-sans-sc-subset.woff")
    html = html.replace("__FONT__", font_data).replace(
        "__FONT_LICENSE__", notice.replace("</script", "<\\/script")
    )
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / "讲稿.md").write_text("\n".join(manuscript), encoding="utf-8")
    report_path = analysis / "分析报告.md"
    report_path.write_text(without_scope(report_path.read_text(encoding="utf-8")), encoding="utf-8")
    metadata = {
        "deck_version": config.DECK_VERSION,
        "created_at": now.isoformat(),
        "slides": len(slides),
        "charts": list(charts),
        "offline": True,
        "source_config": manifest["config_hash"],
        "source_ads_sha256": hashlib.sha256((analysis / "ads.json").read_bytes()).hexdigest(),
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "speech_sha256": hashlib.sha256(
            Path(__file__).with_name("speech.py").read_bytes()
        ).hexdigest(),
        "speech_cjk_characters": sum(
            len(re.findall(r"[\u4e00-\u9fff]", slide["notes"])) for slide in slides
        ),
        "template_sha256": hashlib.sha256(template_path.read_bytes()).hexdigest(),
        "font_license_sha256": hashlib.sha256(
            (assets / "FONT_LICENSE.txt").read_bytes()
        ).hexdigest(),
    }
    (output / "build_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output / "index.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="复用受保护聚合，制作蓝粉HTML答辩演示，不读取数据库。"
    )
    parser.add_argument("--analysis", type=Path, help="已有ADS与manifest的图集目录")
    parser.add_argument("--output", type=Path, help="项目内尚不存在的输出目录")
    parser.add_argument(
        "--replace", action="store_true", help="按最新模板与完整讲稿更新指定既有答辩目录"
    )
    args = parser.parse_args(argv)
    print(
        json.dumps(
            {"presentation": str(build(args.analysis, args.output, replace=args.replace))},
            ensure_ascii=False,
        )
    )
    return 0
