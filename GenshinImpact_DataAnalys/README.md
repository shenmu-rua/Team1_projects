# 原神抽卡数据清洗与可视化

本项目根目录为 `GenshinImpact_DataAnalys/`。上一级 `Team1_projects/` 是容纳多个项目的父目录；
本项目的说明、规范、代码、配置、数据和生成文件统一保存在当前目录内。

当前版本 `0.2.0` 支持本地清洗。明细由本地程序处理，模型、控制台和报告只接收结构、阶段及聚合稽核；
不显示明细行、UID、抽卡 ID 或原始 JSON。原始库只读，清洗结果保存在本项目 `data/` 的独立新库。

## 先读什么

1. [项目约定](AGENTS.md)：当前授权范围及工程规范在原神项目中的适用方式。
2. [参考工程规范](docs/AGENTS.md)及[图表规范](docs/图表规范.md)。
3. [蓝粉主题 skill](theme/SKILL.md)。
4. [结构字典](docs/数据字典.md)及[初始化记录与后续计划](docs/项目初始化.md)。
5. [数据清洗规则](docs/数据清洗.md)：当前清洗口径、运行方式、产物与限制。

`docs/` 原有文档包含信令项目案例，仅作为工程和图表参考；不构成原神数据结论。

## 目录

```text
GenshinImpact_DataAnalys/
├── AGENTS.md                   # 本项目约定和数据访问边界
├── pyproject.toml              # Python 包、依赖分组和检查配置
├── src/genshin_insight/
│   ├── config.py               # 路径、版本、访问模式
│   ├── schema.py               # 只读列结构检查和字典渲染
│   ├── db.py                   # 源库只读与源列允许清单
│   ├── dims.py                 # 不含个人标识的必要维表
│   ├── dwd.py                  # 明细校验、去重、隔离和排序
│   ├── dws.py                  # 从本次清洗结果重建汇总
│   ├── quality.py              # 聚合对账和报告
│   ├── pipeline.py             # 运行调度与产物发布
│   ├── __main__.py             # schema / clean 子命令
│   └── viz/                   # 蓝粉主题适配和保存前自检
├── theme/                      # 已有主题引擎与规范自检，保持单一来源
├── docs/                       # 规范、结构字典与阶段记录
├── test/{unit,contract}/        # 临时空表与合成记录，不连真实库
├── data/                       # 清洗库、报告和本地临时文件，不进 Git
└── gacha_db/                   # 既有本地原始库，只读
```

## 安装与检查

Python 3.11 以上。以下命令从父目录 `Team1_projects/` 开始；进入本项目后，
后续安装与检查命令均在项目根目录执行。建议在独立虚拟环境中安装：

```powershell
cd .\GenshinImpact_DataAnalys
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,viz,analysis]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check src test
.\.venv\Scripts\python -m ruff format --check src test
```

结构检查和清洗仅依赖 Python 标准库；绘图、分析和开发依赖分别放在 `viz`、`analysis`、`dev` 分组。
已有对应环境时，可直接在本目录运行 `python -m pytest`，无需先安装本项目。

命令行安装后：

```powershell
python -m genshin_insight --help
python -m genshin_insight schema
python -m genshin_insight schema --format json
python -m genshin_insight schema --database .\gacha_db\genshin_gacha.db
python -m genshin_insight clean
```

无参数和帮助命令均不打开数据库。`schema` 使用 `mode=ro`、`query_only` 和 SQL 授权器，
只执行 `table_list`、`table_xinfo` 结构检查；不存在的库直接报错，不创建新库。
输出不包含默认表达式、记录示例、计数或统计值。普通表之外的对象会跳过。

`clean` 只读源库，经基础校验、保守去重、冲突隔离和池内排序后重建 DWD/DWS。
新库及同名 JSON、Markdown 汇总报告写入 `data/`，不会覆盖已有文件。
旧 `summary_*` 和 `legacy_*` 不混入本次汇总。完整规则及待复核标记见[数据清洗规则](docs/数据清洗.md)。

未安装项目时，PowerShell 可临时使用源码入口：

```powershell
$env:PYTHONPATH = 'src;.'
python -m genshin_insight --help
```

## 后续绘图入口

清洗已经接入；正式出图前还需建立含小样本抑制的 ADS，并处理类型编码待复核范围。
未来绘图显式调用主题，不在 import 时应用：

```python
from genshin_insight import viz

fonts = viz.apply_theme(width_in=16)
theme = viz.load_theme()
fig = theme.canvas("ppt", width_in=16, height_in=9)

# title_number 由届时获准的聚合过程计算；subtitle 必须说明统计口径。
# top = viz.finish(fig, f"结论包含 {title_number:,} 个记录", subtitle,
#                  theme.source_line(source_name, script_name, config_version))
# ax = theme.axes(fig, top=top)
# 在此绘制获准的聚合结果，颜色取自 theme 的语义常量。
# 连续数值使用 viz.sequential_cmap()；模拟数据须 theme.watermark(fig)。
# viz.save(fig, "image/A01_中文主题.png")  # 自检通过后以 200 dpi 保存
```

当前未运行 notebook 或生成真实数据图。时间时区、物品类型编码和多语言名称的限制见清洗规则。
