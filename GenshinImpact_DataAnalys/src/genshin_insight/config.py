"""项目路径与阶段常量；不在导入时执行文件操作。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
DB_PATH = PROJECT_ROOT / "gacha_db" / "genshin_gacha.db"
DATA_DIR = PROJECT_ROOT / "data"
IMAGE_DIR = PROJECT_ROOT / "image"
DATA_ACCESS_MODE = "schema_only"
THEME_NAME = "bluepink"
CONFIG_VERSION = "0.1.0"
FIGURE_DPI = 200
