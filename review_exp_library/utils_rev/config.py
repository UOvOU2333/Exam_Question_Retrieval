# 子站点配置常量。所有路径基于 app.py 所在目录，不依赖 cwd。

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "data" / "review_library.db"
IMAGE_DIR = BASE_DIR / "static" / "images" / "review_cases"
IMAGE_REL_PREFIX = "static/images/review_cases"

CHIEF_DEFAULT_USERNAME = "chief"
CHIEF_DEFAULT_PASSWORD = "chief123"
