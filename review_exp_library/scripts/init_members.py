"""初始化三位编辑与浏览者账号。幂等。

用法：cd review_exp_library && python scripts/init_members.py
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models_rev.User import User
from models_rev.db import init_db, get_session

EDITORS = [
    ("editor1", "editor123", "编辑一"),
    ("editor2", "editor123", "编辑二"),
    ("editor3", "editor123", "编辑三"),
]
VIEWERS = [
    ("viewer1", "viewer123", "浏览者一"),
]


def main():
    init_db()
    with get_session() as s:
        for username, pwd, disp in EDITORS:
            if not s.query(User).filter_by(username=username).first():
                s.add(User(
                    username=username,
                    password_hash=hashlib.sha256(pwd.encode()).hexdigest(),
                    display_name=disp, role="editor",
                ))
        for username, pwd, disp in VIEWERS:
            if not s.query(User).filter_by(username=username).first():
                s.add(User(
                    username=username,
                    password_hash=hashlib.sha256(pwd.encode()).hexdigest(),
                    display_name=disp, role="viewer",
                ))
    print("初始化完成：1 位总编(chief/chief123) + 3 位编辑 + 1 位浏览者")


if __name__ == "__main__":
    main()
