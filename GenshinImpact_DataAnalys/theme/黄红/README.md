# 黄红 · 图表主题（备选，未接入出图流程）

米黄纸、朱红字、石青作冷色第三笔。这是与项目默认主题「蓝粉」**同构的另一套色板**，平时不用，需要暖调/纸质感/国风版面时再启用。

## 和 theme/（蓝粉）是什么关系

同一套方法和 API，只有配色不同：

| 项 | 结论 |
| --- | --- |
| 语义别名 | 14 个完全一致：`TEXT` `TEXT_SUB` `TEXT_MUTED` `TEXT_FAINT` `ALERT` `WARN` `OK` `MAIN` `MAIN_LIGHT` `MAIN_MID` `PAST` `NOW` `BRIDGE` `GRAY` |
| 公共函数 | 0 个差异（`canvas` `finish` `axes` `hbar` `dumbbell` `label_column` `value_label` `watermark` `save` …） |
| 版式规范 | 完全相同：16 in 画布基准、标题 22 pt、副标题 12 pt、刻度 11.5 pt、数值 12.5 pt、来源 9.5 pt、200 dpi、版心 0.075/0.925 |
| 硬约束 | 共用同一份 `spec_check.py` 逻辑（本目录内自带一份，内容与上层一致） |
| 差别 | 只有色板 |

来源：`分享包/图表主题_蓝粉黄红_精简版.zip → 黄红/`，原样入库，未做修改。

## 当前状态：不参与本项目出图

- 项目默认主题仍是蓝粉：`src/genshin_insight/config.py` 里 `THEME_NAME = "bluepink"`
- `make_charts.py` / `viz.save()` / `spec_check` 全部走 `theme/`（蓝粉）这一层，**不会**读到本目录
- 本目录没有 `__init__.py`，也不是 `theme` 包的子模块，放这儿只是归档

## 想用的时候怎么用

在本目录的**上一级**加一个临时入口即可，不要改动项目的 import 路径：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path("theme/黄红").resolve()))
import theme as T          # 注意：会遮蔽上层 theme 包，只在独立脚本里这样用
import spec_check

T.apply_theme()            # 打印本机生效字体，正常是 ['Noto Sans SC']
fig = T.canvas("ppt", width_in=16, height_in=9)
```

渲染完把这个 `sys.path` 插入去掉，项目其余代码仍用蓝粉。

## 色板速查

| 语义 | 色值 | 说明 |
| --- | --- | --- |
| `MAIN` / `NOW` | `#C74B38` 朱红 | 要读者看的那个 |
| `PAST` | `#3F7078` 石青 | 过去 / 基线 / 唯一能撬开暖底的冷色 |
| `BRIDGE` | `#B8873A` 赭黄 | 冷暖同现时的过渡，也就是名字里的「黄」 |
| `ALERT` | `#9E3355` 绛紫 | 红已是主色，警示必须另起一色 |
| `WARN` / `OK` | `#C8861A` / `#6B8E4E` | 警告 / 通过 |
| 画布 | `#F5F1E6` 米黄、`#FCFAF3` 地面、`#CFC7B4` 轴线 | 暖底，无边框 |
| 文字 | `#2B2A26` / `#4A453C` / `#6E675A` / `#9A9284` | 四级暖调灰阶 |

## 字体

本目录**不含字体文件**（精简版本来就不带）。渲染需要本机有 Noto Sans SC 或思源黑体；项目 `assets/noto-sans-sc-subset.woff` 是网页用子集，matplotlib 读不了，不要拿它替代。

需要随包分发时，用 `分享包/图表主题_蓝粉黄红_含字体.zip`（35 MB，四档字重）。

## 两套能不能混用

版式一致，所以混着用不会"打架"；但**同一份交付物只用一套**，不要一张图冷一张图暖——语义会乱。
