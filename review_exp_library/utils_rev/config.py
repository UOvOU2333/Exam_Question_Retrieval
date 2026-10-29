# 子站点配置常量。所有路径基于 app.py 所在目录，不依赖 cwd。

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.environ.get("REV_DB_PATH", BASE_DIR / "data" / "review_library.db"))
IMAGE_DIR = BASE_DIR / "static" / "images" / "review_cases"
IMAGE_REL_PREFIX = "static/images/review_cases"

ADMIN_DEFAULT_USERNAME = "admin"
ADMIN_DEFAULT_PASSWORD = "admin123"

CHIEF_DEFAULT_USERNAME = "chief"
CHIEF_DEFAULT_PASSWORD = "chief123"

DEFAULT_SUBJECTS = [
    "必修一中特", "必修二经济", "必修三政法", "必修四哲文",
    "选必一国政经", "选必二法律", "选必三逻辑",
]
