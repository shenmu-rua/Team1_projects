# 原神抽卡数据清洗与可视化

本项目根目录为 `GenshinImpact_DataAnalys/`。上一级 `Team1_projects/` 是容纳多个项目的父目录；
本项目的说明、规范、代码、配置、数据和生成文件统一保存在当前目录内。

当前版本 `0.1.0` 只完成工程初始化和结构登记。**数据访问模式：schema_only**。
只允许查看表名、字段及声明约束；包括既有汇总表在内，所有真实记录值均不读取。

## 先读什么

1. [项目约定](AGENTS.md)：当前授权范围及工程规范在原神项目中的适用方式。
2. [参考工程规范](docs/AGENTS.md)及[图表规范](docs/图表规范.md)。
3. [蓝粉主题 skill](theme/SKILL.md)。
4. [结构字典](docs/数据字典.md)及[初始化记录与后续计划](docs/项目初始化.md)。

`docs/` 原有文档包含信令项目案例，仅作为工程和图表参考；不构成原神数据结论。

## 目录

```text
GenshinImpact_DataAnalys/
├── AGENTS.md                   # 本项目约定和数据访问边界
├── pyproject.toml              # Python 包、依赖分组和检查配置
├── src/genshin_insight/
│   ├── config.py               # 路径、版本、访问模式
│   ├── schema.py               # 只读列结构检查和字典渲染
│   ├── __main__.py             # 仅提供 schema 子命令
│   └── viz/                   # 蓝粉主题适配和保存前自检
├── theme/                      # 已有主题引擎与规范自检，保持单一来源
├── docs/                       # 规范、结构字典与阶段记录
├── test/{unit,contract}/        # 仅使用临时 SQLite 空表
└── gacha_db/                   # 既有本地原始库，本阶段只读其结构
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

结构检查仅依赖 Python 标准库；绘图、分析和开发依赖分别放在 `viz`、`analysis`、`dev` 分组。
已有对应环境时，可直接在本目录运行 `python -m pytest`，无需先安装本项目。

命令行安装后：

```powershell
python -m genshin_insight --help
python -m genshin_insight schema
python -m genshin_insight schema --format json
python -m genshin_insight schema --database .\gacha_db\genshin_gacha.db
```

无参数和帮助命令均不打开数据库。`schema` 使用 `mode=ro`、`query_only` 和 SQL 授权器，
只执行 `table_list`、`table_xinfo` 结构检查；不存在的库直接报错，不创建新库。
输出不包含默认表达式、记录示例、计数或统计值。普通表之外的对象会跳过。

未安装项目时，PowerShell 可临时使用源码入口：

```powershell
$env:PYTHONPATH = 'src;.'
python -m genshin_insight --help
```

## 后续绘图入口

只有后续任务明确授权数据处理后，才接入实际清洗和出图。
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

当前没有接入清洗函数、运行 notebook 或生成真实数据图，字段含义和分析口径仍待确认。
