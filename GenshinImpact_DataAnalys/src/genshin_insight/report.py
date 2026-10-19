"""保留用户Word模板的包结构，以发布聚合生成数据质量与分析报告。"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from . import config
from .ads import POOL_NAMES
from .defense import load_release
from .speech import GLOSSARY

TEMPLATE_SHA256 = "c8e76be547092c268c85aa56227c5139f0a7b727ace23c33b1f095d11bca65cb"
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}
CHECK_NAMES = [
    ("输入记录去向对账", "完整性"),
    ("移除原因数量对账", "一致性"),
    ("保留与隔离记录不重叠", "唯一性"),
    ("输入完整进入暂存", "完整性"),
    ("池内序号无断点", "规范性"),
    ("账号卡池汇总总量", "一致性"),
    ("卡池汇总总量", "一致性"),
    ("日汇总总量", "一致性"),
    ("物品汇总总量", "一致性"),
    ("账号卡池星级对账", "一致性"),
    ("卡池星级对账", "一致性"),
    ("外键完整性", "完整性"),
    ("SQLite快速完整性检查", "准确性"),
]


class TemplateReport:
    """复制源组件，修改明确的正文、元数据、字体与图片槽位。"""

    def __init__(self, template: Path):
        from lxml import etree

        self.etree = etree
        if hashlib.sha256(template.read_bytes()).hexdigest() != TEMPLATE_SHA256:
            raise ValueError("模板已变化，需要先重新核对模板槽位与格式。")
        with ZipFile(template) as archive:
            self.parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
        self.original = dict(self.parts)
        self.root = etree.fromstring(self.parts["word/document.xml"])
        self.body = self.root.find("w:body", NS)
        self.source = [deepcopy(el) for el in self.body]
        self.body.clear()
        self.rels = etree.fromstring(self.parts["word/_rels/document.xml.rels"])
        self.picture_id = 200
        self.images = []

    def element(self, tag, **attrs):
        prefix, local = tag.split(":")
        return self.etree.Element(
            f"{{{NS[prefix]}}}{local}",
            {f"{{{NS['w']}}}{key}": str(value) for key, value in attrs.items()},
        )

    def child(self, parent, name, **attrs):
        found = parent.find(name, NS)
        if found is None:
            found = self.element(name, **attrs)
            parent.append(found)
        else:
            for key, value in attrs.items():
                found.set(f"{{{NS['w']}}}{key}", str(value))
        return found

    def content(self, paragraph, value, size=None, bold=False):
        ppr = paragraph.find("w:pPr", NS)
        for el in list(paragraph):
            if el is not ppr:
                paragraph.remove(el)
        run = self.element("w:r")
        rpr = self.element("w:rPr")
        rpr.append(
            self.element(
                "w:rFonts",
                ascii="TeX Gyre Termes",
                hAnsi="TeX Gyre Termes",
                eastAsia="Noto Serif CJK SC",
                cs="TeX Gyre Termes",
            )
        )
        if size is not None:
            rpr.extend(
                [
                    self.element("w:sz", val=round(size * 2)),
                    self.element("w:szCs", val=round(size * 2)),
                ]
            )
        if bold:
            rpr.extend([self.element("w:b"), self.element("w:bCs")])
        run.append(rpr)
        for i, line in enumerate(str(value).split("\n")):
            if i:
                run.append(self.element("w:br"))
            text = self.element("w:t")
            text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            text.text = line
            run.append(text)
        paragraph.append(run)
        return paragraph

    def p(self, value, *, role=50, size=12, bold=False, page=False):
        paragraph = self.content(deepcopy(self.source[role]), value, size, bold)
        ppr = self.child(paragraph, "w:pPr")
        self.child(ppr, "w:widowControl")
        if page:
            self.child(ppr, "w:pageBreakBefore")
        self.body.append(paragraph)
        return paragraph

    def h(self, value, level=2, *, page=False):
        paragraph = self.p(
            value,
            role=46 if level == 1 else 47,
            size=16 if level == 1 else 14,
            bold=True,
            page=page or level == 1,
        )
        self.child(self.child(paragraph, "w:pPr"), "w:keepNext")
        return paragraph

    def caption(self, value, figure=False):
        return self.p(value, role=75 if figure else 56, size=10.5, bold=True)

    def table(self, headers, rows, widths, *, caption=None):
        if caption:
            self.caption(caption)
        table = deepcopy(self.source[57])
        for el in list(table):
            if el.tag not in {f"{{{NS['w']}}}tblPr", f"{{{NS['w']}}}tblGrid"}:
                table.remove(el)
        grid = table.find("w:tblGrid", NS)
        grid.clear()
        for width in widths:
            grid.append(self.element("w:gridCol", w=width))
        templates = self.source[57].findall("w:tr", NS)
        for i, row in enumerate([headers, *rows]):
            tr = self.element("w:tr")
            trpr = self.element("w:trPr")
            trpr.append(self.element("w:cantSplit"))
            if i == 0:
                trpr.append(self.element("w:tblHeader"))
            tr.append(trpr)
            for j, value in enumerate(row):
                source_cell = templates[0 if i == 0 else 1].findall("w:tc", NS)[min(j, 4)]
                cell = deepcopy(source_cell)
                tcpr = cell.find("w:tcPr", NS)
                self.child(tcpr, "w:tcW", w=widths[j], type="dxa")
                self.child(
                    tcpr,
                    "w:shd",
                    fill="1F4E79" if i == 0 else "FFFFFF" if i % 2 else "F5F8FC",
                    val="clear",
                    color="auto",
                )
                for el in list(cell):
                    if el is not tcpr:
                        cell.remove(el)
                paragraph = self.content(deepcopy(source_cell.find("w:p", NS)), value, 10.5, i == 0)
                self.child(
                    self.child(paragraph, "w:pPr"),
                    "w:jc",
                    val="center" if i == 0 or j == 0 else "left",
                )
                self.child(
                    paragraph.find("w:r/w:rPr", NS), "w:color", val="FFFFFF" if i == 0 else "1A1A1A"
                )
                cell.append(paragraph)
                tr.append(cell)
            table.append(tr)
        self.body.append(table)
        self.p("", size=3)
        return table

    def figure(self, path: Path, caption: str):
        from PIL import Image

        paragraph = deepcopy(self.source[74])
        self.child(self.child(paragraph, "w:pPr"), "w:keepNext")
        self.child(
            self.child(paragraph, "w:pPr"),
            "w:spacing",
            line=240,
            lineRule="auto",
            before=60,
            after=60,
        )
        self.picture_id += 1
        rid = f"rIdReport{self.picture_id}"
        name = f"report_{path.stem}.png"
        relation = self.etree.Element(
            "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
            Id=rid,
            Type=NS["r"] + "/image",
            Target=f"media/{name}",
        )
        self.rels.append(relation)
        self.parts[f"word/media/{name}"] = path.read_bytes()
        with Image.open(path) as image:
            width, height = image.size
        cx, cy = round(15.4 * 360000), round(15.4 * 360000 * height / width)
        for blip in paragraph.findall(".//a:blip", NS):
            blip.set(f"{{{NS['r']}}}embed", rid)
        for extent in [
            *paragraph.findall(".//wp:extent", NS),
            *paragraph.findall(".//a:xfrm/a:ext", NS),
        ]:
            extent.set("cx", str(cx))
            extent.set("cy", str(cy))
        for props in paragraph.findall(".//wp:docPr", NS):
            props.set("id", str(self.picture_id))
            props.set("name", path.stem)
            props.set("descr", caption)
        self.body.append(paragraph)
        self.caption(caption, True)
        self.images.append({"code": path.stem, "caption": caption, "file": name, "width_cm": 15.4})

    def front(self, data, audit):
        values = {
            0: "文档编号：GI-DQ-2026-001",
            1: "使用范围：课程项目汇报与答辩",
            3: "DATA  QUALITY  ASSESSMENT  REPORT",
            5: "原神抽卡记录",
            6: "数据质量分析报告",
            7: "Data Quality Assessment of Genshin Gacha Records",
            12: "原神数据分析项目组",
            13: "二〇二六年十月",
        }
        for i in range(15):
            el = deepcopy(self.source[i])
            if i in values:
                old_run = el.find("w:r/w:rPr", NS)
                size_el = None if old_run is None else old_run.find("w:sz", NS)
                size = int(size_el.get(f"{{{NS['w']}}}val")) / 2 if size_el is not None else 10.5
                old = deepcopy(old_run) if old_run is not None else None
                self.content(el, values[i], size, i in {5, 6, 12})
                if old is not None:
                    color = old.find("w:color", NS)
                    if color is not None:
                        el.find("w:r/w:rPr", NS).append(deepcopy(color))
                if i == 6:
                    self.child(self.child(el, "w:pPr"), "w:pStyle", val="Title")
            if i == 10:
                pairs = [
                    "原神公开抽卡留存记录",
                    "2020年12月至2022年7月",
                    "清洗产物与主分析03的发布聚合",
                    "V1.0",
                    "原神数据分析项目组",
                    "2026年10月19日",
                ]
                for row, value in zip(el.findall("w:tr", NS), pairs, strict=True):
                    self.content(row.findall("w:tc", NS)[1].find("w:p", NS), value, 10.5)
            self.body.append(el)
        self.p("文 档 信 息", role=31, size=16, bold=True)
        self.table(
            ["项目", "内容"],
            [
                ["文档名称", "原神抽卡数据质量分析报告"],
                ["文档编号", "GI-DQ-2026-001"],
                ["版本与日期", "V1.0  2026年10月19日"],
                ["编制", "原神数据分析项目组"],
                ["清洗规则", audit["rule_version"]],
                ["图表配置", "0.3.0+3cee80f4"],
                ["主要结论", "工程对账通过；在明确观察口径的前提下，可用于样本内描述性分析"],
            ],
            [1800, 7226],
        )
        self.p("修订记录", role=34, size=12, bold=True)
        self.table(
            ["版本", "日期", "修订说明", "编制"],
            [
                [
                    "V1.0",
                    "2026-10-19",
                    "按指定写作模板整理清洗、稽核、七图分析与适用性结论",
                    "项目组",
                ]
            ],
            [800, 1500, 5526, 1200],
        )
        self.p("阅读说明", role=37, size=12, bold=True)
        self.p(
            "本报告区分两种统计口径：清洗执行指标覆盖本次全部处理记录；分析图表固定使用主分析03。二者数值不同源于来源选择，不能解释为清洗遗漏。正文不设置数据集范围对照章节。"
        )
        self.p(
            "全部数字取自已发布聚合及清洗稽核，不展示真实账号、抽卡标识、原始明细或原始JSON。库中时间未注明时区，本报告不将其换算为北京时间。"
        )
        self.p(
            "DQ-01至DQ-13为程序执行的自动稽核；DQ-14至DQ-20为根据稽核与分析口径登记的质量评估。通过、警告、不通过表示质量结论，问题的关闭状态另行登记。"
        )
        self.p("目　　录", role=43, size=16, bold=True)
        self.body.append(deepcopy(self.source[44]))
        self.body.append(deepcopy(self.source[45]))

    def save(self, output: Path):
        self.body.append(deepcopy(self.source[289]))
        self.parts["word/document.xml"] = self.xml(self.root)
        self.parts["word/_rels/document.xml.rels"] = self.xml(self.rels)
        for name in [
            "word/document.xml",
            "word/styles.xml",
            "word/header1.xml",
            "word/header2.xml",
            "word/footer1.xml",
            "word/footer2.xml",
        ]:
            root = self.etree.fromstring(self.parts[name])
            for fonts in root.findall(".//w:rFonts", NS):
                fonts.attrib.clear()
                for key, value in {
                    "ascii": "TeX Gyre Termes",
                    "hAnsi": "TeX Gyre Termes",
                    "eastAsia": "Noto Serif CJK SC",
                    "cs": "TeX Gyre Termes",
                }.items():
                    fonts.set(f"{{{NS['w']}}}{key}", value)
            for shade in root.findall(".//w:rPr/w:shd", NS):
                shade.getparent().remove(shade)
            for text in root.findall(".//w:t", NS):
                if text.text:
                    text.text = (
                        text.text.replace("【数据集名称】", "原神抽卡记录")
                        .replace("【密级】", "项目汇报")
                        .replace("【版本】", "V1.0")
                    )
            self.parts[name] = self.xml(root)
        settings = self.etree.fromstring(self.parts["word/settings.xml"])
        self.child(settings, "w:updateFields", val="true")
        self.parts["word/settings.xml"] = self.xml(settings)
        fonts = self.etree.fromstring(self.parts["word/fontTable.xml"])
        for el in list(fonts):
            fonts.remove(el)
        for name in ["Noto Serif CJK SC", "TeX Gyre Termes"]:
            fonts.append(self.element("w:font", name=name))
        self.parts["word/fontTable.xml"] = self.xml(fonts)
        core = self.etree.fromstring(self.parts["docProps/core.xml"])
        for el in core:
            local = self.etree.QName(el).localname
            if local in {"creator", "lastModifiedBy"}:
                el.text = "原神数据分析项目组"
            elif local == "title":
                el.text = "原神抽卡数据质量分析报告"
        self.parts["docProps/core.xml"] = self.xml(core)
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            for name, content in self.parts.items():
                archive.writestr(name, content)

    def xml(self, root):
        return self.etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)


def compose(report: TemplateReport, data: dict, audit: dict, manifest: dict, figures: list[Path]):
    """按原模板十章与四个附录组织事实、方法、结果和质量处置。"""
    p, h, table = report.p, report.h, report.table
    m, scope = audit["metrics"], data["scope"]
    pools = {row["pool_group"]: row for row in data["pools"]}
    role = pools[301]
    share = 100 * role["pulls"] / scope["pulls"]
    months = max(
        (row for row in data["months"] if row["pulls"] is not None), key=lambda row: row["pulls"]
    )
    clock = max(
        (row for row in data["clock"] if row["pulls"] is not None), key=lambda row: row["pulls"]
    )
    rates = [row for row in data["rates"] if row["pool_group"] == 301]
    q1, q4 = (
        min(rates, key=lambda row: row["quartile"]),
        max(rates, key=lambda row: row["quartile"]),
    )
    total5 = sum(row["star5"] for row in data["pools"])
    item_share = 100 * sum(row["pulls"] for row in data["items"]) / total5
    duplicate_rate = 100 * m["duplicate_rows_removed"] / m["input_pulls"]
    warnings = [
        (
            "DQ-14",
            "唯一性",
            "重复记录",
            f"移除{m['duplicate_rows_removed']:,}条重复业务ID记录，占输入{duplicate_rate:.4f}%",
            "重复规则已执行并对账；保留原始层以便追溯",
            "已关闭",
        ),
        (
            "DQ-15",
            "准确性",
            "同秒顺序歧义",
            f"全量清洗标记{m['ambiguous_same_second_pulls']:,}条；主分析核心三池涉及歧义记录{data['gap_quality']['ambiguous_pulls']:,}条",
            "保留歧义标记；五星间隔仅使用排序明确的账号池组合",
            "已规避",
        ),
        (
            "DQ-16",
            "准确性",
            "物品类型编码",
            f"{m['item_type_review_sources']:,}个来源的{m['item_type_review_pulls']:,}条记录标为待复核",
            "不翻转类型码，不以其区分角色和武器；待来源方确认",
            "待确认",
        ),
        (
            "DQ-17",
            "时效性",
            "时区与时间覆盖",
            "无时区时间；起止月可能不完整；缺少曝光天数与完整历史说明",
            "按原时间自然月聚合，不作时区换算和活跃度推断",
            "待确认",
        ),
        (
            "DQ-18",
            "一致性",
            "多语言名称与别名",
            "名称按原始字符串精确汇总，未建立统一实体映射",
            "名称榜按原始名称解释，不直接命名为角色人气榜",
            "已披露",
        ),
        (
            "DQ-19",
            "代表性",
            "样本选择机制",
            "缺少抽样框、纳入机制与总体对照信息",
            "结论限定为留存记录样本，不扩推全部玩家",
            "待确认",
        ),
        (
            "DQ-20",
            "代表性",
            "五星间隔观察机制",
            "只观察相邻已记录五星的闭合间隔，首段、尾段与历史缺失受限",
            "排除首段和未闭合尾段；不用于官方概率或真实保底推断",
            "已披露",
        ),
    ]
    report.front(data, audit)
    h("1　报告概述", 1)
    h("1.1　编制目的")
    p(
        "本报告用于项目汇报与答辩，说明原神抽卡记录如何经过只读清洗、质量稽核和受保护汇总，形成可复算的统计图表。评估既关注记录是否被正确处理，也关注字段语义、观察覆盖与样本选择对结论的限制。"
    )
    p(
        f"清洗运行处理{m['input_pulls']:,}条输入，保留{m['kept_pulls']:,}条，13项工程稽核通过。主分析03含{scope['people']:,}个账号、{scope['pulls']:,}条留存记录。报告据此评价卡池构成、时间集中和分布特征，明确后续分析需要补充的证据。"
    )
    h("1.2　评估依据与方法")
    p(
        "本次沿用模板的完整性、规范性、唯一性、一致性、准确性、时效性和代表性维度，具体判定以项目清洗规则1.0.0及已发布ADS为依据。模板中的信令示例、数据量、地理判断和行业术语均不作为本项目证据；本报告不作外部标准认证声明。"
    )
    table(
        ["结论", "判定含义", "使用要求"],
        [
            ["通过", "既定程序断言与期望一致", "在当前检查覆盖内继续发布"],
            ["警告", "存在已处理异常、语义疑点或观察边界", "保留证据，执行规避或明确披露"],
            ["不通过", "关键断言失败或无法满足发布条件", "停止发布并修复；本次未出现"],
        ],
        [1000, 4200, 3826],
        caption="表 1-1　质量状态判定标准",
    )
    h("1.3　数据处理流程")
    p(
        "原始SQLite以只读模式打开，先检查必要结构与关联，再在项目内的新库中完成基础校验、两层保守去重、冲突隔离与池内排序，形成DWD明细和DIM维表。DWS从本次明细重新汇总，ADS再执行小样本保护。制图、答辩与本报告复用同次发布聚合。"
    )
    table(
        ["层或环节", "职责", "主要控制"],
        [
            ["原始层", "保留交付状态", "只读；不读取UID、个人源路径或原始JSON/BLOB"],
            ["DWD与DIM", "校验、去重、隔离与排序", "每条输入只有一个去向；保留复核标记"],
            ["DWS", "账号卡池、卡池、日期、物品汇总", "重新计算，避免混用历史summary与legacy"],
            ["ADS与交付", "受保护聚合、图表及报告", "5个贡献账号门槛、互补抑制与来源清单"],
        ],
        [1900, 3000, 4126],
        caption="表 1-2　数据分层与质量控制",
    )

    h("2　评估结论摘要", 1)
    h("2.1　总体结论")
    p(
        "本报告登记20项质量评估，其中13项通过、7项警告、0项不通过。前13项为清洗程序的自动稽核；后7项为结合稽核事实和分析定义作出的质量评估，不计入程序执行检查数。总体判断为有条件使用。",
        bold=True,
    )
    p(
        "工程层面的输入去向、汇总总量、序号与关联检查均满足既定断言。仍需保留的限制集中于类型编码、无时区时间、多语言名称、样本选择与观察历史。通过工程稽核说明处理过程自洽，并不能证明采样完整、字段含义完全可靠或样本可代表全部玩家。"
    )
    table(
        ["指标", "数值", "统计口径"],
        [
            ["输入记录", f"{m['input_pulls']:,}条", "本次全量清洗"],
            ["保留记录", f"{m['kept_pulls']:,}条", "本次全量清洗"],
            [
                "移除重复",
                f"{m['duplicate_rows_removed']:,}条  {duplicate_rate:.4f}%",
                "比例分母为输入记录",
            ],
            ["冲突隔离", f"{m['conflicting_rows_quarantined']:,}条", "本次已识别冲突"],
            ["自动稽核", "13项通过  0项失败", "与清洗JSON中的checks对应"],
            ["主分析记录", f"{scope['pulls']:,}条", "主分析03，固定来源口径"],
            ["主分析账号", f"{scope['people']:,}个", "来源内去重，不跨来源合并"],
        ],
        [2200, 3000, 3826],
        caption="表 2-1　关键质量与分析指标",
    )
    h("2.2　主要发现")
    p(
        f"角色活动祈愿占主分析留存抽数的{share:.1f}%，是记录量最大的卡池。{months['month']}单池月记录达到{months['pulls'] / 10000:.1f}万抽。账号留存抽数中位数为{data['volume_median']:,.0f}抽。以上结果描述记录构成和样本分布，不换算玩家消费或总体活跃。"
    )
    h("2.3　优先事项")
    p(
        "后续优先向来源方确认物品类型编码、时间字段时区、历史导出的覆盖规则和样本纳入机制，并建立可追溯的多语言实体映射。在这些信息补齐前，继续采用现有规避规则和解释边界。"
    )

    h("3　数据结构与观察口径", 1)
    h("3.1　核心字段画像")
    p(
        "本节依据结构字典、清洗表定义与稽核描述字段。当前发布产物未提供逐字段缺失数和唯一值总数，因此不填入未经计算的画像数字，也不展示明细示例。结构约束和记录级校验结果不能替代原始字段逐列完整性统计。"
    )
    table(
        ["字段", "类型", "含义与处理", "使用约束"],
        [
            ["dataset_id", "INTEGER", "来源分组", "分析固定为03"],
            ["player_id", "INTEGER", "来源内账号关联键", "仅本地使用，不对外发布"],
            ["item_id", "INTEGER", "物品身份关联键", "不自动合并多语言实体"],
            [
                "gacha_type与pool_group",
                "INTEGER",
                "原卡池代码与合并池组",
                "301/400按角色活动池合并",
            ],
            ["gacha_time", "TEXT", "统一为秒级无时区字符串", "不推断时区"],
            ["pool_seq", "INTEGER", "账号池内重建连续序号", "间隔基于记录序号"],
            ["item_type_review", "INTEGER", "类型待复核标记", "不得作为已核实类型使用"],
            ["time_order_ambiguous", "INTEGER", "同秒顺序歧义标记", "间隔分析排除对应账号池"],
        ],
        [2300, 1200, 2850, 2676],
        caption="表 3-1　核心字段与使用约束",
    )
    h("3.2　时间字段与记录覆盖")
    p(
        f"主分析记录时间从{scope['first_time']}至{scope['last_time']}。清洗统一字符串格式并验证日历合法性，本次时间规范化变更{m['timestamp_normalized_pulls']:,}条。时间未附时区信息，不能直接认定为UTC或北京时间；起止月也不能假定完整。"
    )
    p(
        "月度图按原时间自然月聚合，星期小时图按库中字符串直接解析。缺口不插值，也未按不同星期、小时的可观察天数进行曝光校正，因此时间高值只用于描述留存记录集中程度。"
    )

    h("4　核心明细表质量评估", 1)
    h("4.1　完整性与关联")
    p(
        f"输入去向和暂存对账均为{m['input_pulls']:,}条，与期望一致；保留与隔离记录交集为0。外键错误为0，SQLite快速完整性检查达到期望结果。上述证据支持本次处理没有在既定流程中丢失输入，并不证明源系统已经导出全部历史。"
    )
    h("4.2　规范性与排序")
    p(
        f"日期、来源行、关联键与ID格式按清洗规则校验。抽卡ID始终作为文本处理，数字顺序通过长度与字典序实现，避免浮点转换损失精度。清洗后池内序号从1连续重建，序号断点为0，原序号发生调整的记录共{m['sequence_changed_pulls']:,}条。"
    )
    p(
        f"全量清洗中有{m['ambiguous_same_second_pulls']:,}条记录带同秒顺序歧义标记。该标记来源于同一账号池同秒存在缺失ID的多条记录；保留稳定顺序不等于确认真实秒内顺序。主分析核心三池的歧义记录为{data['gap_quality']['ambiguous_pulls']:,}条，间隔聚合仍按规则排除不满足条件的账号池组合。"
    )
    h("4.3　唯一性与冲突隔离")
    p(
        f"先按来源位置识别重复或冲突，再按账号内业务ID检查。同一键且内容相同只保留一条；同一键且内容矛盾则全部隔离。本次移除{m['duplicate_rows_removed']:,}条重复业务ID记录，冲突隔离{m['conflicting_rows_quarantined']:,}条。无ID记录不按时间与物品外观强行去重，以免误删十连中合法的同秒同物品记录。"
    )
    h("4.4　一致性与语义准确性")
    p(
        f"四张DWS汇总总量均为{m['kept_pulls']:,}条，账号卡池与卡池星级对账异常数均为0。另一方面，{m['item_type_review_sources']:,}个来源的{m['item_type_review_pulls']:,}条保留记录被标为类型待复核。本报告按星级、卡池和原始名称组织分析，不自动翻转类型码或将待复核编码解释为可信分类。"
    )

    h("5　数据清洗与处理结果", 1)
    h("5.1　清洗规则与执行结果")
    table(
        ["规则或指标", "结果", "处理决定"],
        [
            [
                "基础校验",
                "最终移除原因中仅出现duplicate_gacha_id",
                "不额外推断未统计的字段级缺失率",
            ],
            ["重复业务ID", f"{m['duplicate_rows_removed']:,}条", "保留同内容的一条，登记其余原因"],
            ["冲突记录", f"{m['conflicting_rows_quarantined']:,}条", "规则为冲突候选全部隔离"],
            [
                "时间规范化",
                f"{m['timestamp_normalized_pulls']:,}条变更",
                "不增加未经证实的时区偏移",
            ],
            ["池内序号重建", f"{m['sequence_changed_pulls']:,}条变更", "保留原序号作本地追溯"],
            ["类型待复核", f"{m['item_type_review_pulls']:,}条", "保留标记，不按类型码分类"],
            ["保留总量", f"{m['kept_pulls']:,}条", "输入等于保留加移除，检查通过"],
        ],
        [2400, 2500, 4126],
        caption="表 5-1　清洗执行结果",
    )
    h("5.2　明细设计与数据保护")
    p(
        "原库保持只读，清洗写入独立新库。DWD保留必要内部追溯键、池内序号及复核标记，不保留真实UID和原始抽卡ID。DWS仍包含本地账号粒度，不能直接作为对外交付。ADS发布时以5个贡献账号为门槛；不足门槛的度量和人数一起隐藏，必要时执行互补抑制或合并相邻区间。"
    )
    h("5.3　流水线与复现")
    p(
        f"处理依次由clean、make_charts.py、make_defense.py及make_report.py显式运行，本地import复用各层逻辑，路径使用pathlib，导入不连接数据库或读取业务文件。图表配置为{manifest['settings']['version']}+{manifest['config_hash']}，清洗规则为{audit['rule_version']}。清单保留来源文件元信息、配置和代码哈希；文件元信息用于区分输入，不等同全库内容哈希。"
    )

    h("6　维度与参考数据质量评估", 1)
    h("6.1　维表关联与卡池映射")
    p(
        "DIM提供来源、账号、物品和卡池描述。明细必须能关联有效维表，来源所属账号与数据集也必须一致。外键稽核异常为0，但关联成立只说明键在当前模型中一致，不证明所有描述字段的业务含义均已获得来源方确认。"
    )
    table(
        ["维度", "采用口径", "可信度与限制"],
        [
            ["卡池", "采用源卡池维表；301/400合并角色池", "分组一致性有校验，仍保留原卡池编码"],
            ["星级", "采用合法的3、4、5星值", "用于记录内星级计数与对账"],
            ["物品名称", "仅去首尾空白后精确汇总", "翻译与别名未合并，不等同统一实体"],
            ["物品类型", "保留来源编码和复核标记", "部分来源待确认，不用于本次分类"],
            ["来源与账号", "仅在来源内使用内部键", "不跨来源合并为独立玩家总数"],
        ],
        [1600, 3526, 3900],
        caption="表 6-1　维度采用口径",
    )
    h("6.2　历史汇总与版本甄别")
    p(
        "旧summary与legacy表未混入本次事实汇总，避免历史筛选条件不明或重复累计。DWS由本次清洗后的DWD重建。多语言名称的合并属于后续实体映射工作，不能在本轮凭名称相似性自动完成；每项映射应保留依据和版本。"
    )

    charts = [
        (
            "7.1　卡池构成与五星占比",
            "图 7-1　卡池构成与记录内五星占比",
            "上下独立面板分别表示各池抽数和该池五星记录占比，横轴均从0开始，颜色保持卡池固定映射。",
            f"角色活动池共{role['pulls']:,}抽，占主分析{share:.1f}%；记录内五星数{role['star5']:,}，对应占比{100 * role['star5'] / role['pulls']:.2f}%。",
            "汇总总量已对账通过；五星占比仍受记录缺失、账号选择与观察长度影响。",
            "可用于描述样本卡池构成，不能用作官方出金概率、市场份额或消费份额。",
        ),
        (
            "7.2　月度记录分布",
            "图 7-2　各卡池月度留存抽数",
            "四个面板表示四类卡池；横轴为自然月，纵轴为万抽，各池纵轴尺度独立，空缺保持空缺。",
            f"{months['month']}的{POOL_NAMES[months['pool_group']]}达到单池月度峰值{months['pulls'] / 10000:,.1f}万抽。",
            "时区、导出覆盖与曝光基数未确认，起止月可能不完整，判定为警告。",
            "仅说明留存记录高值，不能仅据时间对应关系归因于版本、活动或玩家活跃。",
        ),
        (
            "7.3　星期小时集中程度",
            "图 7-3　星期与小时留存记录热力矩阵",
            "上下矩阵分别显示00至11时、12至23时。格内数字单位为万抽，共用单粉色对数色阶，色条仍标实际数值。",
            f"周二18时累计{clock['pulls'] / 10000:.1f}万抽，占全部主分析抽数{100 * clock['pulls'] / scope['pulls']:.1f}%。",
            "时间按无时区字符串直接解析，未按可观察天数校正；该统计不等于活跃人数或在线时长。",
            "可定位留存记录集中时段；进一步解释前需要时区、覆盖天数和事件口径。",
        ),
        (
            "7.4　账号留存记录量",
            "图 7-4　账号记录量与分箱累计分布",
            "上方横条为各抽数区间的账号占比，下方折线为各分箱上界内的累计占比；末端为开放区间。",
            f"账号留存抽数中位数为{data['volume_median']:,.0f}抽，抽数不超过1,000的账号占{100 * sum(row['counts'][0] for row in data['volume_bins'] if row['hi'] is not None and row['hi'] <= 1000) / scope['people']:.1f}%。",
            "分箱总人数与主分析账号总数一致。累计线基于已发布安全分箱，不还原个人散点。",
            "用于比较记录量分布；记录量不等于账号完整历史、投入或付费金额。",
        ),
        (
            "7.5　记录量分组与五星占比",
            "图 7-5　账号记录量分组的五星占比分布",
            "各池分别按账号抽数四分组，Q1至Q4由低到高；点为组内账号占比中位数P50，线为P25至P75，每个账号等权。",
            f"角色池Q4组中位数为{q4['median']:.2f}%，P25至P75为{q4['q25']:.2f}%至{q4['q75']:.2f}%；Q1、Q4的IQR分别约{q1['q75'] - q1['q25']:.2f}和{q4['q75'] - q4['q25']:.2f}个百分点。",
            "重复分位边界会合并，新手池退化为一组。P25至P75是分位区间，不能当作置信区间。",
            "图示分布差异；不能解释为抽数或付费提高概率。Q1、Q2等不是第一季度、第二季度。",
        ),
        (
            "7.6　记录内相邻五星间隔",
            "图 7-6　记录内已闭合五星间隔分布",
            "间隔为同一账号池内相邻已记录五星的序号差；三个池分别归一为占比，稀疏尾部按各池条件合箱。",
            f"角色池分析{sum(row['counts'][301] for row in data['gap_bins'][301]):,}段已闭合间隔，其中71至80抽箱占{100 * next(row['counts'][301] for row in data['gap_bins'][301] if row['lo'] == 71 and row['hi'] == 80) / sum(row['counts'][301] for row in data['gap_bins'][301]):.1f}%，中位数所在箱的上界为80抽。",
            "首个五星之前的片段与未出现后继五星的尾段未计入；历史缺失无法被当前口径完全识别。",
            "结果是留存记录内的闭合间隔分布，不能作为真实保底、首五星等待时间或官方机制证明。",
        ),
        (
            "7.7　五星原始名称记录榜",
            "图 7-7　五星原始名称出现次数",
            "横条按五星原始名称的留存次数排序，第一名强调显示，角色和武器均可进入；未合并多语言别名。",
            f"前{len(data['items'])}个原始名称覆盖{item_share:.1f}%的五星记录；其中{data['items'][0]['name']}为{data['items'][0]['pulls']:,}次。",
            "各名称满足贡献人数保守下界不少于5的发布门槛；类型待复核编码未参与分类。",
            "仅作为原始名称频数榜；解释人气需要统一实体、曝光机会和样本选择证据。",
        ),
    ]
    h("7　分析结果与样本观察", 1)
    for i, (title, caption, reading, finding, quality, impact) in enumerate(charts):
        h(title, page=i > 0)
        report.figure(figures[i], caption)
        for label, value in [
            ("读图方式", reading),
            ("关键发现", finding),
            ("质量判断", quality),
            ("对分析的影响", impact),
        ]:
            p(f"{label}：{value}")

    h("8　数据适用性评估", 1)
    h("8.1　观察密度与适用前提")
    p(
        f"主分析可见{scope['people']:,}个账号、{scope['pulls']:,}条抽卡记录，但不同账号的留存长度差异明显，中位数仅描述当前记录量。时间跨度、记录数或序号连续性都不能单独证明历史导出完整，内存或数据库中的连续序号也不能补回源历史缺口。"
    )
    h("8.2　可以回答与不能回答的问题")
    table(
        ["分析方向", "可以回答", "不能回答及原因"],
        [
            [
                "卡池构成",
                "样本记录中各池的抽数与星级构成",
                "总体市场、消费份额；缺少抽样框与投入数据",
            ],
            ["时间分布", "留存记录的月度和星期小时高值", "活跃及事件因果；缺少时区与曝光基数"],
            [
                "账号分布",
                "记录量分箱、中位数与组内占比分布",
                "完整历史、消费及概率因果；观察长度不同",
            ],
            ["五星间隔", "已闭合且排序明确的记录内间隔", "真实保底、首五星等待；删失与缺失未解决"],
            ["名称频数", "原始字符串的出现次数", "实体角色人气；别名和曝光未统一"],
        ],
        [1400, 3300, 4326],
        caption="表 8-1　分析能力与解释边界",
    )
    p(
        "使用时须保持固定来源、卡池合并、账号等权、间隔资格和隐私保护规则。外推结论、类型分类与强机制推断应在补齐证据并更新规则后另行评估。"
    )

    h("9　问题清单与整改建议", 1)
    h("9.1　问题登记")
    p(
        "责任角色为建议分工，不代表来源方已经承诺整改。警告级别与问题关闭状态分别管理：已清除的重复仍保留质量发现，已披露的解释边界也不因工程对账通过而消失。"
    )
    table(
        ["问题", "关联", "主要措施", "建议责任角色", "状态"],
        [
            [
                f"P-{i:02d} {row[2]}",
                row[0],
                row[4],
                "项目组" if i in {1, 2, 7} else "来源方与项目组",
                row[5],
            ]
            for i, row in enumerate(warnings, 1)
        ],
        [2100, 900, 3400, 1426, 1200],
        caption="表 9-1　问题与整改清单",
    )
    h("9.2　需来源方确认的事项")
    p(
        "需要确认物品类型0和1在各来源中的编码含义，提供统一的名称与物品身份映射；说明时间时区、导出工具的历史保留和截断条件、账号纳入与排除规则，以及缺失ID的生成原因。确认材料应保留版本和来源，避免仅靠经验或名称外观修改定义。"
    )
    h("9.3　持续监控建议")
    p(
        "后续每次运行继续要求13项工程断言全部通过，并跟踪重复、冲突、类型待复核、排序歧义和ADS隐藏格数量。对于新出现的冲突、关联错误和汇总不平衡，停止发布；对新增编码、名称与时间格式，先复核再更新配置。趋势告警阈值应基于多次运行的历史分布校准，当前不虚设经验百分比。"
    )

    h("10　结论", 1)
    p(
        f"本次清洗从{m['input_pulls']:,}条输入中保留{m['kept_pulls']:,}条，移除{m['duplicate_rows_removed']:,}条重复，13项自动稽核全部通过。处理去向、序号、关联和各层汇总在已定义检查范围内自洽，原始层继续作为追溯依据。"
    )
    p(
        f"主分析03显示，角色活动祈愿贡献{share:.1f}%的留存抽数，{months['month']}单池月记录为{months['pulls'] / 10000:.1f}万抽，账号留存抽数中位数为{data['volume_median']:,.0f}抽。账号分组、已闭合五星间隔和原始名称榜为样本内部比较提供了进一步证据。"
    )
    p(
        "报告的质量结论为有条件使用。类型编码、时区和历史覆盖、实体名称与样本选择仍限制解释力度。现阶段可交付样本内描述性分析；官方概率、真实保底、消费水平、总体活跃和角色人气等结论需要额外证据。"
    )
    p(
        "建议优先补齐类型字典、时间与历史导出说明和样本纳入规则，同时保留现有保护措施。获得新证据后沿相同流水线重新计算，使新增结论能够追溯到明确的规则和输入版本。"
    )

    h("附录 A　数据质量检查明细", 1)
    p(
        "以下13项与清洗JSON中的checks顺序一一对应。编号由本报告登记，actual与expected分别为实际值与期望值。"
    )
    table(
        ["编号", "检查项", "实际与期望", "状态", "证据键"],
        [
            [
                f"DQ-{i:02d}",
                CHECK_NAMES[i - 1][0],
                f"{row['actual']:,} / {row['expected']:,}",
                "通过" if row["passed"] else "不通过",
                row["check"],
            ]
            for i, row in enumerate(audit["checks"], 1)
        ],
        [850, 2250, 2200, 900, 2826],
        caption="表 A-1　自动化工程稽核",
    )
    h("质量评估与解释边界", page=True)
    table(
        ["编号与维度", "检查项", "证据与结论", "处理决定"],
        [[f"{row[0]}\n{row[1]}", row[2], f"警告。{row[3]}", row[4]] for row in warnings],
        [1300, 1600, 3100, 3026],
        caption="表 A-2　语义与适用性质量评估",
    )

    h("附录 B　字段可信度字典", 1)
    table(
        ["字段或概念", "可信度", "依据与使用建议"],
        [
            ["dataset_id与卡池分组", "已验证关联", "结构、分组校验与外键对账；保持来源口径"],
            ["player_id", "已验证内部键", "来源内关联使用；不推断跨来源同一玩家"],
            ["gacha_time", "格式已校验\n时区未知", "按无时区字符串解析；不按UTC+8修正"],
            ["gacha_id", "格式与精确排序", "仅清洗本地处理，未复制进DWD，不公开标识值"],
            ["pool_seq", "重建规则已验证", "连续性通过；不表示完整源历史"],
            ["rank_type", "结构与汇总已验证", "合法星级范围及汇总对账；非官方概率证据"],
            ["item_type", "部分来源待确认", "保留标记；当前不做可信角色武器分类"],
            ["name", "原始字符串可信", "允许精确频数统计；实体映射待补充"],
            ["time_order_ambiguous", "规则标记", "用于排除顺序不明的账号池组合"],
            ["ADS贡献人数", "口径分项定义", "月份、名称与间隔箱取保守下界，不能相加推算独立人数"],
        ],
        [2200, 2100, 4726],
        caption="表 B-1　字段与指标可信度",
    )

    h("附录 C　图表索引与复核说明", 1)
    table(
        ["图号", "图名", "发布图源", "关联"],
        [
            [
                f"图 7-{i}",
                item[1].split("　", 1)[1],
                f"A{i:02d}.png",
                "DQ-06至13"
                if i == 1
                else "DQ-17、19"
                if i in {2, 3}
                else "DQ-18、19"
                if i == 7
                else "DQ-15、20"
                if i == 6
                else "DQ-19",
            ]
            for i, item in enumerate(charts, 1)
        ],
        [1000, 4000, 1600, 2426],
        caption="表 C-1　报告图表索引",
    )
    h("C.1　图表复核说明")
    p(
        "七张图从同次已发布ADS重新按A4版心排版，图宽15.4厘米、200dpi，实际刻度字号不小于8磅。热力矩阵按小时分为上下两块以保证数字可读，仍共用相同色阶；其余指标、分母、分组和隐私门槛保持一致。图表保存前执行项目主题禁止项检查，无双Y轴。"
    )
    p(
        "Q01来源范围对照图仅为内部诊断，按既定汇报要求不纳入本报告。主分析账号数、抽数及日期仅在必要的统计口径处说明。原模板的信令示例图和写作指引不构成本报告内容。"
    )
    h("C.2　来源与复现")
    p(
        f"聚合来源为image/analysis_20261019_final/ads.json，图表配置{manifest['settings']['version']}+{manifest['config_hash']}。自动稽核来源为对应清洗运行的JSON报告。执行make_report.py通过本地import调用模板填充与报告图表；不连接原始库或清洗库。本次构建的模板与聚合哈希保存在报告目录的build_manifest.json。"
    )

    h("附录 D　术语与缩写", 1)
    entries = []
    for entry in GLOSSARY:
        if isinstance(entry, dict):
            entries.append(
                [entry.get("term", ""), entry.get("meaning", entry.get("definition", ""))]
            )
        else:
            entries.append([entry[0], entry[1]])
    table(["术语", "说明"], entries, [2000, 7026], caption="表 D-1　统计与工程术语")


def build(template: Path, analysis: Path, output: Path) -> Path:
    """输出DOCX及来源清单，保留模板未修改部件的字节内容。"""
    from .viz.report_plots import generate

    template, analysis, output = (
        template.resolve(strict=True),
        analysis.resolve(strict=True),
        output.resolve(),
    )
    if not all(path.is_relative_to(config.PROJECT_ROOT.resolve()) for path in (analysis, output)):
        raise ValueError("分析输入和报告输出必须位于本项目内部。")
    if output.exists():
        raise FileExistsError("报告输出目录已存在，不能覆盖既有交付。")
    data, audit, manifest = load_release(analysis)
    report = TemplateReport(template)
    output.mkdir(parents=True)
    figures = generate(
        data, output / "figures", manifest["settings"]["version"] + "+" + manifest["config_hash"]
    )
    compose(report, data, audit, manifest, figures)
    document = output / "原神抽卡数据质量分析报告.docx"
    report.save(document)
    changed = [name for name, value in report.original.items() if report.parts[name] != value]
    metadata = {
        "template_sha256": TEMPLATE_SHA256,
        "ads_sha256": hashlib.sha256((analysis / "ads.json").read_bytes()).hexdigest(),
        "source_config": manifest["config_hash"],
        "rule_version": audit["rule_version"],
        "technical_checks": 13,
        "assessment_items": 20,
        "pass": 13,
        "warning": 7,
        "fail": 0,
        "figures": report.images,
        "changed_template_parts": changed,
        "preserved_parts_sha256": {
            name: hashlib.sha256(value).hexdigest()
            for name, value in report.original.items()
            if name not in changed
        },
        "field_refresh": "Word refresh required before final delivery",
        "code_sha256": {
            "report.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "report_plots.py": hashlib.sha256(
                Path(__file__).with_name("viz").joinpath("report_plots.py").read_bytes()
            ).hexdigest(),
        },
    }
    (output / "build_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="按指定Word模板导出原神数据质量与分析报告，只读发布聚合。"
    )
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument(
        "--analysis", type=Path, default=config.IMAGE_DIR / "analysis_20261019_final"
    )
    parser.add_argument(
        "--output", type=Path, default=config.PRESENTATION_DIR / "quality_report_20261019"
    )
    args = parser.parse_args(argv)
    print(build(args.template, args.analysis, args.output))
    return 0
