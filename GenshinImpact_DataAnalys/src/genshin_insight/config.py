"""项目路径与阶段常量；不在导入时执行文件操作。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
DB_PATH = PROJECT_ROOT / "gacha_db" / "genshin_gacha.db"
DATA_DIR = PROJECT_ROOT / "data"
IMAGE_DIR = PROJECT_ROOT / "image"
DATA_ACCESS_MODE = "local_cleaning"
SCHEMA_ACCESS_MODE = "schema_only"
THEME_NAME = "bluepink"
CONFIG_VERSION = "0.2.0"
CHART_CONFIG_VERSION = "0.3.0"
CLEANING_RULE_VERSION = "1.0.0"
ID_REQUIRED_DATASET_IDS = (3,)
FIGURE_DPI = 200
PRESENTATION_DIR = PROJECT_ROOT / "reports"
DECK_VERSION = "1.3.0"
DASHBOARD_VERSION = "1.0.0"
