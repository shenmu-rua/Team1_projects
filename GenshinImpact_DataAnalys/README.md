# 原神抽卡数据清洗与可视化

本项目根目录为 `GenshinImpact_DataAnalys/`。上一级 `Team1_projects/` 是容纳多个项目的父目录；
本项目的说明、规范、代码、配置、数据和生成文件统一保存在当前目录内。

清洗版本 `0.2.0`、图表配置 `0.3.0`。明细由本地程序处理，模型、控制台和报告只接收结构、阶段及受保护聚合；
不显示明细行、UID、抽卡 ID 或原始 JSON。原始库只读，清洗结果保存在本项目 `data/` 的独立新库。

## 先读什么

1. [项目约定](AGENTS.md)：当前授权范围及工程规范在原神项目中的适用方式。
2. [参考工程规范](docs/AGENTS.md)及[图表规范](docs/图表规范.md)。
3. [蓝粉主题 skill](theme/SKILL.md)。
4. [结构字典](docs/数据字典.md)及[初始化记录与后续计划](docs/项目初始化.md)。
5. [数据清洗规则](docs/数据清洗.md)：当前清洗口径、运行方式、产物与限制。
6. [图表制作说明](docs/图表制作.md)：分析范围、完整制作入口、保护措施与图集口径。

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
│   ├── ads.py                  # 分析聚合与小样本保护
│   ├── charts.py               # 图集制作调度
│   ├── __main__.py             # schema / clean / charts 子命令
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
python -m genshin_insight charts
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

## 制作分析图集

安装依赖后，在本目录运行：

```powershell
python -m genshin_insight charts
# 或显式指定清洗库；输出目录必须尚不存在且位于本项目内部
python -m genshin_insight charts --database .\data\genshin_clean_<运行编号>.db --output .\image\my_analysis
```

未安装本地包时先设置 `$env:PYTHONPATH = 'src;.'`。也可在 Python 中直接调用：

```python
from genshin_insight.charts import generate

output = generate()  # 默认选择本项目最新清洗库、主分析数据集03
```

入口通过本地 `import` 复用聚合、绘图和主题，使用 `pathlib` 管理文件，不引入 `os`。
一次生成八张16:9、200 dpi的PNG，以及 `ads.json`、`manifest.json`、`分析报告.md`，
位于 `image/analysis_<运行编号>/`。每张图保存前执行主题自检，没有双Y轴。
主分析固定来源口径；小样本在ADS层保护；时间、名称、概率与记录完整性的限制直接写在图上。

## HTML汇报答辩

安装 `.[analysis,viz,presentation]` 后，从已有图集制作离线演示：

```powershell
python -m genshin_insight defense --analysis .\image\analysis_20261019_final
```

入口通过本地 `import` 调用 `genshin_insight.defense.build()`，只读取受保护ADS与清洗聚合稽核，
不连接数据库。生成29页16:9单文件HTML、逐页讲稿和构建清单，放在本项目 `reports/defense_<运行时间>/`。
HTML内嵌七张SVG、官网原神艺术字与开源字体子集，可以单独复制后离线打开。分析报告和答辩已移除Q01数据集范围章节。

导航栏默认隐藏，按`H`显示，再按一次隐藏。方向键或空格翻页，`O`打开目录，`N`查看当前页讲稿，`F`全屏；支持打印为PDF。
图表及解读覆盖项目流程、清洗实现、ADS保护、蓝粉主题和每张图的统计含义。

讲稿按29页一一对应，可直接口播，包含开场、解释、翻页过渡和结束致谢；首次出现时解释术语，附录保留术语速查，最末尾附16组答辩问题与参考回答，均不增加PPT页面。
第28页用一页简要展示刘沐泽、桂曙光、丁振儒、许宏达的主要职责，第29页只显示THANKS。分工页与简短口播共用`team.py`，不展示工时和占比。
演示已移除名称榜口径解读、主要结论与解释边界、答辩常见问题、复现入口与后续完善四页，七张分析图保留。
Q1～Q4表示按账号抽数划分的四组；组内P25/P50/P75与IQR另行解释。
需要按最新内容更新已有答辩目录时显式使用：

```powershell
python -m genshin_insight defense --analysis .\image\analysis_20261019_final --output .\reports\defense_20261019_final --replace
```

## 答辩开场视频

`reports/opener_20261019_final/开场视频.mp4` 为1920×1080、60fps的H.264/AAC短片，
保留原有40秒文字和图表时间线，随后以1.2秒完成视频自身的入门白场，基础片长41.2秒。
现成片在白场后接入BV16j411B7si第一段“直接启动”的前2秒，隐藏标识下方提示文字，
再用1.6秒将原神标识缩小移动到首页位置，同时渐显首页，停留约0.6秒后接入演示，总长约45.4秒。
视频片头与片尾标题中的“原神”采用官方原始标识素材，统一显示为白色艺术字，并同步标题发光效果。
背景和原声均使用用户提供的夜间开门视频，从源视频75.2秒裁到116.4秒，原速播放；
取消旧星空背景的缩放、漂移、脉冲和叠光，不混入原开场配乐。
依次展示主分析记录规模、卡池构成、月度峰值、账号记录量和五星原始名称榜。
所有数字来自既有受保护ADS，不连接数据库。

打开同目录 `index.html`，点击“播放开场”，图表前景39.6–40秒淡出，40秒起不再有任何文字、
图表或暗化遮罩；跳过按钮同步隐藏。播放器逐帧测量成片的白光覆盖率，约40.39–40.85秒随门内
白光连续放大视频至覆盖窗口，在约40.97–41.15秒的稳定白场内恢复比例。播放不自动切换浏览器全屏；
视频和窗口空白区域的底色按成片边缘颜色同步。随后播放标识转场，无黑帧接入预加载的现有29页答辩，
也可提前跳过片头。
此入口与 `defense_20261019_final/` 保持相邻；MP4可独立播放。交付目录只保留成片、播放入口、
海报、使用说明、构建清单和字体许可。视频采用H.264 CRF 23 / slow、AAC 160k压缩，保留1080p与60fps。

安装 `.[analysis,viz,presentation,motion]`、本地Node.js的 `playwright` 包及Chrome后，在本项目运行：

```powershell
python -m genshin_insight opener --background-video "原视频的绝对路径.mp4" --source-end 116.4 --output .\reports\opener_new
```

源码通过本地import组织：`opener.py`负责聚合选取、视频原声裁切和发布，
`viz/opener.html`负责透明图表前景，`viz/render_opener.cjs`用本地Chrome导出前景，
由FFmpeg与60fps背景合成，保留同段原声。背景副本、透明动画母版及字体子集只写
项目 `.pytest_cache/`，正常构建结束后自动删除；不在交付目录存放重复背景和配乐。
可通过 `--ffmpeg`、`--node` 指定可执行文件；`--prepare-only`保留项目缓存中的可定位母版并输出其路径。
如Node包未安装在项目 `node_modules/`，运行前用 `NODE_PATH` 指向已有包目录。

为未拼接的基础开场加入标识转场：

```powershell
python -m genshin_insight opener-transition --opener "基础开场.mp4" --logo-video "启动素材.mp4" --deck .\reports\defense_20261019_final\index.html --output .\reports\opener_with_transition --source-url "https://www.bilibili.com/video/BV16j411B7si/"
```

`opener_transition.py`和`viz/render_transition.cjs`仅重新编码新转场，既有开场及音轨直接拼接。
首页标识的位置从现有HTML实际渲染结果测量，末帧与实时演示对齐。若首页版式变化，应重新制作转场。

## 按Word模板导出报告

安装 `.[analysis,viz,report]` 后，在本项目中执行：

```powershell
python -m genshin_insight report --template "模板的绝对路径.docx" --output .\reports\quality_report_new
```

`report`子命令通过本地import调用`report.py`填充模板，保留封面、分节页码、标题、表格与目录控件；
正文包含十章、七张A4图和四个附录，解释清洗方法、质量结论、图表含义及Q1/Q2等术语。
它只读取已有ADS和清洗聚合稽核，不连接数据库。`viz/report_plots.py`保持蓝粉主题，
图宽15.4厘米、200dpi，实际刻度不小于8磅，不使用双Y轴。

构建清单记录模板、ADS和代码哈希，以及保留的模板包部件哈希。重建带同模板清单的目录须显式传入`--replace`。
目录和页码须经Microsoft Word原生更新后完成交付检查；本次定稿已完成更新和逐页渲染验证。
