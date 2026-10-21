# 原神课程项目代码与复现

代码快照来自2026年10月21日现有项目，只有项目代码、配置、测试与规范，不含数据库、明细、压缩包、Git元数据或运行缓存。安装、测试与运行均进入本目录执行。

## 环境

Python 3.11以上。依赖分组见pyproject.toml；图集发布环境记录为Python 3.14.6、pandas 3.0.5、NumPy 2.4.6、Matplotlib 3.11.0。安装Noto Sans SC或思源黑体；报告正文样式指定Noto Serif CJK SC。随包PDF已完成字体与逐页版式检查，跨设备以PDF效果为准。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,analysis,viz,presentation,report]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check src test
```

## 从既有原始导入库重跑

根据数据来源说明获得已许可的SQLite库，放到本目录gacha_db/genshin_gacha.db。这个路径是输入位置，不代表材料包附带数据库。源库只读；不运行历史导入脚本，不解压来源压缩包。

```powershell
.\.venv\Scripts\python -m genshin_insight clean --output .\data\course_clean_new.db
.\.venv\Scripts\python -m genshin_insight charts --database .\data\course_clean_new.db --output .\image\course_analysis_new
.\.venv\Scripts\python -m genshin_insight defense --analysis .\image\course_analysis_new --output .\reports\course_defense_new
```

这些输出路径必须尚不存在；再次运行时更换名称。清洗记录各步骤和最终去向，13项稽核通过才发布。charts重算受保护ADS与八张内部图，其中Q01只用于内部诊断，不进入正式分析报告和答辩。

## 报告与模板

两份报告使用`01_自建报告模板`中的模板排版，正文数字、表格与插图依据`../06_复现依据`中的受保护聚合、清洗稽核和报告插图编排，不连接数据库。模板中的封面信息、目录域和页码已用Microsoft Word更新，PDF由同一文档导出。

若分析数据重新生成，应同步替换复现依据中的ADS、清洗稽核、发布清单与七张A4报告图，不得只替换数字或只换图。A4图由`src/genshin_insight/viz/report_plots.py`的`generate(data, output, version)`生成，图宽15.4厘米、200 dpi。更新模板或插图后，用Microsoft Word更新目录和域并重新导出PDF。

## 追溯

图集原发布清单记录结果生成时的代码哈希。核心ads.py、viz绘图和蓝粉主题与图集发布版本一致。数字依据为已发布聚合；本次没有重新清洗约1,580万条明细。

仓库：https://github.com/shenmu-rua/Team1_projects ，子目录GenshinImpact_DataAnalys。当前材料没有自动提交、推送，也没有复制.git。测试只用合成记录或临时空表。
