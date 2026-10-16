# Team1_projects

原神抽卡数据分析项目，包含分析脚本、概率计算工具、SQLite 数据库构建脚本、说明文档和绘图资源。

## 目录

- `GenshinImpact_DataAnalys/GI_gacha_dataset-main/`：原始数据集的分析脚本与说明。
- `GenshinImpact_DataAnalys/GI_gacha_dataset-main/dp_calculator/`：角色池、武器池概率计算与绘图工具。
- `GenshinImpact_DataAnalys/gacha_db/`：SQLite 数据库构建脚本和读取示例，详见[数据库说明](GenshinImpact_DataAnalys/gacha_db/README.md)。

## 数据文件

本仓库不包含抽卡数据、统计 JSON、NPY 数组、生成的数据库、导入报告或压缩包；这些文件已加入 `.gitignore`，本地文件仍保留。克隆仓库后，需要自行准备对应数据才能运行依赖数据的脚本。

数据库构建所需的本地目录结构：

```text
GenshinImpact_DataAnalys/
├── GI_gacha_dataset-main/
│   ├── GI_gacha_dataset_02/         # 各账号目录及 CSV
│   └── GI_gacha_dataset_03/         # 原始 ZIP 分卷及配套索引、统计文件
└── gacha_db/
    ├── build_db.py
    └── read_db_example.py
```

准备好数据后，在仓库根目录运行：

```powershell
python .\GenshinImpact_DataAnalys\gacha_db\build_db.py
python .\GenshinImpact_DataAnalys\gacha_db\read_db_example.py
```

`build_db.py` 仅依赖 Python 标准库；读取示例使用 pandas，绘图功能还需要 Matplotlib。其他分析脚本的依赖和数据要求见各目录中的说明。

原数据来源及使用说明保留在[数据集说明](GenshinImpact_DataAnalys/GI_gacha_dataset-main/readme.md)和[数据集 03 说明](GenshinImpact_DataAnalys/GI_gacha_dataset-main/GI_gacha_dataset_03/readme.md)中。
