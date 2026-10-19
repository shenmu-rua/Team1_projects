# 原神抽卡数据分析：项目约定

本项目将原神抽卡记录整理为可追溯的清洗、汇总和图表流程。
工程基线为 `docs/AGENTS.md`，图表基线为 `docs/图表规范.md`，主题实现为
`theme/SKILL.md`。先读这些文件，再修改项目。

## 目录边界

本项目根目录是 `GenshinImpact_DataAnalys/`。上一级 `Team1_projects/` 是多项目父目录，
不放本项目的业务说明、阶段记录或专属配置。新文件和生成文件均放在本项目内部，
本项目的数据与压缩包忽略规则由本目录 `.gitignore` 管理。

理由：用户要求父目录用于当前和后续项目，具体项目内容必须收在各自子目录。

## 当前授权范围

- 用户已明确要求“清洗数据”，当前允许 **local_cleaning**：由本地程序处理明细，输出清洗产物与聚合稽核。
- 用户进一步授权分析与制图：允许本地程序只读清洗库，模型、图片和报告只接收受保护聚合；不以明细探索替代本地聚合。
- 不把真实明细、UID、抽卡 ID、源文件中的个人路径或原始 JSON/BLOB 返回模型、日志或报告。
- 人工检查只看结构、计数与稽核汇总；不执行 head/tail/随机抽样，不打印异常记录值。
- 原始 SQLite 库只读，清洗结果写本项目 `data/` 下的新库，不覆盖原库或已有清洗库。
- 不解压原始压缩包，不运行 `gacha_db/build_db.py`、读取示例或旧分析程序。
- 结构检查仍使用 `genshin_insight.schema.inspect_schema`，其授权器仍只允许表结构。
- 清洗连接另外限制源表和源列，不读取 UID、player_key、原始 JSON、资源 BLOB 或历史汇总值。

理由：本次“清洗数据”授权本地程序执行必要处理；此前仅表头的约束继续用于模型可见内容，
原始标识和明细不离开本地处理过程。授权不扩展到重新解压、重新导入或跨项目访问。

## 参考规范在本项目中的适用方式

`docs/` 保留的是 signal-insight 信令项目参考材料。其西塔案例、发现、数据量、
日期、IMSI 规则、既有测试数量和主题注册系统不是原神项目的事实，不得直接沿用。
本项目包名为 `genshin_insight`，发行名为 `genshin-insight`。

理由：复用工程约定，业务结论和数据口径必须重新建立证据。

## 文件位置与依赖

| 职责 | 位置 | 规范依据 |
| --- | --- | --- |
| 路径、访问模式、版本等常量 | `src/genshin_insight/config.py` | 第 2、3 条 |
| 只读表结构检查和结构字典渲染 | `src/genshin_insight/schema.py` | 第 2、15.3 条 |
| 清洗连接与源列访问限制 | `src/genshin_insight/db.py` | 第 1、2、7 条 |
| 维表、明细清洗、汇总 | `src/genshin_insight/dims.py`、`dwd.py`、`dws.py` | 第 2、5 条 |
| 稽核和聚合报告 | `src/genshin_insight/quality.py` | 第 2 条 |
| 清洗调度与产物发布 | `src/genshin_insight/pipeline.py` | 第 2、3 条 |
| 命令行入口 | `src/genshin_insight/__main__.py` | 第 2 条，单独管理调用方式 |
| 图表主题接入和保存前检查 | `src/genshin_insight/viz/` | 第 2、12 条 |
| 图表应用层聚合及小样本保护 | `src/genshin_insight/ads.py` | 第 1、2、5 条 |
| 图集调度与短入口 | `src/genshin_insight/charts.py`、`make_charts.py` | 第 2、3 条；用户要求本地 import |
| HTML答辩制作与短入口 | `src/genshin_insight/defense.py`、`make_defense.py` | 第 2、12 条；复用已发布ADS |
| 完整逐页口播与术语说明 | `src/genshin_insight/speech.py` | 第 2 条；内容与演示版式分别维护 |
| 开场片制作调度、原创配乐 | `src/genshin_insight/opener.py`、`score.py`、`make_opener.py` | 第 2、3 条；只复用发布ADS，本地import |
| 开场片动画、播放器与编码 | `src/genshin_insight/viz/opener*.html`、`render_opener.cjs` | 第 2、12 条；40秒原生图表动画，16:9 |
| Word模板填充与报告制作 | `src/genshin_insight/report.py`、`make_report.py` | 第 2、3、15.1 条；只读取已发布ADS与聚合稽核 |
| A4报告图表适配 | `src/genshin_insight/viz/report_plots.py` | 第 2、12 条；15.4厘米物理宽度，实际刻度不小于8磅 |
| 答辩版式、交互与字体许可 | `src/genshin_insight/viz/defense.html`、`font_license.txt` | 第 2、12 条；沿用蓝粉主题 |
| 既有蓝粉引擎与自检 | `theme/` | `theme/SKILL.md`，保持单一来源 |
| 字段字典、口径与阶段记录 | `docs/` | 第 15.3 条及现有文档目录 |
| 单元与契约测试 | `test/unit/`、`test/contract/` | `docs/测试说明.md` |

依赖向下：入口 → charts → ads / viz → config；viz.plots 只引用 ADS 名称常量；config 不导入项目模块。
import 时不连接数据库、不读业务文件、不建目录、不修改绘图参数、不打印。
不创建 `utils.py`、`common.py`、`helper.py`、`misc.py`。

理由：按修改原因拆分，避免导入行为触发数据访问。

## 后续数据与图表

- 原始库和 `ods_` 只读；后续清洗写独立产物，按 `dwd_`、`dim_`、`dws_`、`ads_` 分层。
- UID、抽卡记录标识、源路径等可能关联个人的内容不得进入图表、日志或版本库。
- 数据、压缩包、数据库、notebook 输出和生成图不提交；不向模型打印明细内容。
- 使用蓝粉主题。颜色按角色固定；只用开源字体；200 dpi；PPT 严格 16:9。
- 答辩开场短片经用户明确授权自由发挥视觉主题，采用深色星空和金色主强调；统计图仍遵守零基线、单轴、保护聚合与来源可追溯要求。既有PPT继续使用蓝粉主题。
- 图表调用 `viz.finish()`，标题数字来自计算，副标题说明口径，来源可追溯。
- 保存统一调用 `viz.save()` 先自检；模拟数据必须加水印。
- 分析报告与答辩不包含Q01数据集范围章节；Q01仅保留为内部图集诊断。HTML只复用受保护ADS和清洗聚合报告，图表导出带可编辑文字的SVG。
- 主题与参考规范的差异记录在 `docs/项目初始化.md`，不假设四套参考主题已实现。

理由：保留原始依据、保护标识、让同一交付物的口径和视觉一致。

## 验证与 Git

- 测试仅使用临时 SQLite 空表或明确合成的虚构记录，不连接真实库；真实运行只输出聚合对账。
- 在本目录运行 `python -m pytest`；风格检查为 `python -m ruff check src test`。
- 提交前 `git status` 并点名文件，不使用 `git add .`。提交格式遵守参考规范第 14 条。
- 保留用户既有改动和删除；本次初始化不自动提交、推送或恢复旧文件。

理由：测试可复现，初始化不产生隐含的数据读取或版本控制操作。
