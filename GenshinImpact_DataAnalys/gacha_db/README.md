# 原神抽卡 SQLite 数据库

`genshin_gacha.db` 是可独立复制使用的 SQLite 数据库，整合 `GI_gacha_dataset-main` 中两批抽卡记录。读取数据库不需要数据库服务，也不需要再次解压源数据。原始目录未改动。

## 本次导入结果

| 数据集 | 账号标识数 | 抽卡记录数 | 五星记录数 |
| --- | ---: | ---: | ---: |
| GI_gacha_dataset_02 | 175 | 208,262 | 3,321 |
| GI_gacha_dataset_03 | 16,289 | 15,599,315 | 257,304 |
| 合计 | 16,464 | 15,807,577 | 260,625 |

数据库约 **1.88 GiB**（2,015,395,840 字节），收录 277 种“名称＋类别＋星级”组合和 23 个配套资源文件。30 个空 CSV 已登记，未出现结构不合法的隔离行。SQLite 完整性、外键、全部汇总总量及数据集 03 逐账号抽数／五星数对账均通过。

需后续清洗时核查的标记如下，均保留原记录：

- 同一账号内抽卡编号重复：511 条后续重复行，涉及 1 个账号。
- 源记录时间回退：1 处，涉及 1 个账号；`pool_seq` 已按时间等字段排序。
- 类别编码与三星组合可疑：2,425 条，涉及 7 个账号；详见下文第 10 条规则。

合计账号数未在两批来源之间推定身份或去重；汇总数包含上述被标记的记录。

## 文件

- `genshin_gacha.db`：明细、维度、汇总、质量记录和原始配套资源。
- `import_report.json`：本次导入的实际行数、时间范围、异常统计、校验结果、数据库大小及 SHA-256。
- `build_db.py`：可重复构建脚本，仅依赖 Python 标准库；直接读取带密码的 ZIP 分卷。
- `read_db_example.py`：使用 pandas 分块读取的示例；加 `--plot` 可用 Matplotlib 生成抽数概览图。

## 快速读取

```python
from pathlib import Path
import sqlite3
import pandas as pd

db = Path(r"C:\Users\shenmu\Desktop\GenshinImpact_DataAnalys\gacha_db\genshin_gacha.db")
with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
    overview = pd.read_sql_query("SELECT * FROM v_dataset_summary", conn)
    pools = pd.read_sql_query("SELECT * FROM v_pool_summary", conn)
    print(overview)
    print(pools)
```

明细从 `v_pulls` 读取即可，不必手工连接各维度表。建议先在 SQL 中筛选，再分块读取；全量记录不适合一次性装入 DataFrame。

```python
with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
    # player_id 是数据库内部账号主键，两批数据之间不会串号。
    player_id = conn.execute(
        "SELECT min(player_id) FROM players WHERE dataset_id=3"
    ).fetchone()[0]

    for part in pd.read_sql_query(
        """SELECT * FROM v_pulls
           WHERE player_id=? AND pool_group=301
           ORDER BY pool_seq""",
        conn,
        params=(player_id,),
        chunksize=100_000,
        dtype={"gacha_id": "string"},
        parse_dates=["gacha_time"],
    ):
        # 在这里清洗、提取特征或统计；不要逐块累积回一个巨大列表。
        print(part.head())
```

运行示例：

```powershell
python .\gacha_db\read_db_example.py
python .\gacha_db\read_db_example.py --plot
```

## 表与视图

| 名称 | 内容 |
| --- | --- |
| `v_pulls` | 推荐的明细读取入口，包含账号、道具、星级、时间、卡池和来源 |
| `v_dataset_summary` | 各数据集账号数、抽数、五星数、起止时间 |
| `v_pool_summary` | 各数据集原始卡池的抽数、星级分布和样本五星比例 |
| `pulls` | 规范化的逐抽事实表 |
| `players` | 账号维度，唯一键为 `(dataset_id, player_key)` |
| `items` | 道具维度，唯一键为 `(name, item_type, rank_type)` |
| `gacha_types` | 原始卡池编号及合并分组 |
| `datasets` | 数据集介绍及原说明中的规模和截止日期 |
| `summary_pool` | 按数据集、原始卡池汇总 |
| `summary_player_pool` | 按账号、合并卡池汇总，可用于筛选样本 |
| `summary_daily` | 按数据集、日期、原始卡池、星级、道具类别汇总 |
| `summary_item` | 按数据集、原始卡池、道具汇总 |
| `source_files` | 每个源文件／压缩成员的路径、所属账号、SHA-256、编码、导入行数和状态 |
| `quality_issues` | 重复编号、编号冲突、源顺序时间回退等问题；关联源文件和行号 |
| `rejected_rows` | 结构不合法而无法写入事实表的行，保存原字段及原因 |
| `legacy_player_index` | 原 `player_index.csv` 的结构化副本，用于逐账号对账 |
| `legacy_histograms` | 原 4 个 JSON 统计结果的结构化副本；保留全部零频率区间 |
| `resource_assets` | 原说明、脚本、JSON、索引 CSV、NPY 数组及字体／SVG 等配套文件的原始字节 |
| `metadata` | 构建版本、身份与排序规则、来源说明和内嵌导入报告 |

`v_pulls` 的主要字段：

| 字段 | 含义 |
| --- | --- |
| `pull_id` | 数据库内部逐抽主键 |
| `dataset` | `GI_gacha_dataset_02` / `GI_gacha_dataset_03` |
| `player_id`, `player_key` | 内部账号主键、原文件名／文件夹标识 |
| `uid_suffix` | 仅数据集 03 的账号标识后四位，不能单独作为账号唯一键 |
| `name` | 道具名称 |
| `gacha_type` | 原始卡池编号，保留 100、200、301、302、400 |
| `pool_group` | 分析分组：仅将 400 归为 301，便于连续分析角色活动池 |
| `item_type`, `item_type_name` | 按常见源编码解释为 0＝角色、1＝武器；另提供中文类别，异常编码见下文 |
| `rank_type` | 3 / 4 / 5 星 |
| `gacha_id` | 原始抽卡编号，以 **TEXT** 保存；数据集 02 没有该字段，值为 NULL |
| `gacha_time` | 原时间字符串 `YYYY-MM-DD HH:MM:SS`，未推定或转换时区 |
| `pool_seq` | 在账号和合并卡池内按时间、数值抽卡编号、原行号排序后的序号 |
| `source_file_id`, `source_file`, `source_row` | 源文件主键、原路径、CSV 行号；表头为第 1 行 |

已建立账号＋分组＋序号、原始卡池＋道具、抽卡时间等索引。日趋势、星级比例及道具计数优先读取汇总表，可避免扫描全部明细。

## 保留和清洗规则

1. **不自动删除重复记录或按游戏机制过滤样本。** 结构合法的记录全部保留；可疑记录写入 `quality_issues`，结构不合法的行写入 `rejected_rows`。汇总包含所有成功导入行。
2. 数据集 02 中的空 CSV 作为空文件登记。空文件不等于账号无抽卡；账号仍按原目录标识保留。
3. 仅统一列名、数值类型、道具类别和首尾空白。若修剪了字段空白，质量表保留该行原字段。源 CSV 的字节级校验值保存在 `source_files`；源抽卡 CSV 未在数据库中再存一份完整 BLOB。
4. 同一秒可有多抽，同名同时间的记录可能来自十连，因此不能依靠“时间＋道具名称”直接去重。数据集 02 无原始抽卡编号，同秒内部顺序采用源文件行序。
5. 数据集 03 使用完整文件名标识账号，不能按后四位 UID 合并账号；两批数据中的账号也未推定为同一个人。因此合计账号数是两批账号标识数之和，不代表已跨数据集去重的人数。
6. `pool_seq=1` 仅表示现有记录的起点。原记录可能有缺失，不能直接把起点视为保底重置；保底分析需要另行定义截断与缺失规则。301/400 分组用于共同序列，原始池编号仍可单独筛选。
7. 原 JSON 是作者分析程序产生的历史过滤结果，说明中提到默认忽略首个五星和最后 100 抽；它与本库全量明细汇总的口径不同，不应相加。
8. `observed_star5_rate` 是样本中的五星占比。来源是玩家自愿公开的部分记录，不能直接当作官方基础概率或无偏总体估计。
9. 数据集 03 的原说明限定学习交流用途；原始说明已嵌入数据库，后续汇报应保留数据来源及采样局限。
10. 源数据存在多语言道具名称，本次未合并中英文等别名。部分英文记录出现 `item_type=0` 且 `rank_type=3` 的组合，按常见编码会被解释成三星角色，已标记 `three_star_character`；这提示源文件可能采用了不同的类别编码。此类账号的四／五星记录也应一并核查，不能只修正已标记的三星行。

查看异常：

```sql
SELECT issue_code, count(*) FROM quality_issues GROUP BY issue_code;
SELECT * FROM rejected_rows LIMIT 20;
SELECT f.relative_path, q.source_row, q.issue_code, q.details_json
FROM quality_issues q JOIN source_files f USING(source_file_id)
LIMIT 50;

-- 找出类别编码需要进一步核查的账号，而非只筛出已标记的三星行。
SELECT DISTINCT p.player_id, p.player_key
FROM quality_issues q JOIN source_files f USING(source_file_id)
JOIN players p USING(player_id)
WHERE q.issue_code='three_star_character';
```

按日期分析角色池抽数（同时包括 301／400，按数据集分别统计）：

```sql
SELECT d.code AS dataset, s.pull_date, sum(s.pulls) AS pulls,
       sum(CASE WHEN s.rank_type=5 THEN s.pulls ELSE 0 END) AS star5
FROM summary_daily s JOIN datasets d USING(dataset_id)
WHERE s.gacha_type IN (301,400)
GROUP BY d.code, s.pull_date
ORDER BY d.code, s.pull_date;
```

从数据库恢复原 NPY 概率数组：

```python
from io import BytesIO
import numpy as np

with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
    blob = conn.execute(
        """SELECT a.content FROM resource_assets a
           JOIN source_files f USING(source_file_id)
           WHERE f.relative_path=?""",
        ("dp_calculator/character.npy",),
    ).fetchone()[0]
array = np.load(BytesIO(blob), allow_pickle=False)
```

## 重建与校验

在项目根目录运行：

```powershell
python .\gacha_db\build_db.py
# 已有目标文件时，验证新库成功后才替换：
python .\gacha_db\build_db.py --overwrite
```

可用 `--source`、`--output` 指定其他目录／文件。分卷密码取自原说明，默认 `OneBST`。构建先写 `*.building.db`，通过校验后才发布目标数据库；失败时保留临时文件供诊断，重新运行前应先重命名该临时文件。

导入校验包括：SQLite 完整性、所有外键、源行数＝导入行数＋隔离行数、各层汇总与事实表总行数一致，以及数据集 03 逐账号的四类池抽数／五星数与原 `player_index.csv` 对账。原索引起止时间的差异单独记录为质量问题。

`import_report.json` 的 `database_sha256` 可用于复制后的文件校验。数据库内嵌报告不含数据库自身的最终哈希和文件大小，这些值在关闭最终文件后写入外部报告，避免自引用。
