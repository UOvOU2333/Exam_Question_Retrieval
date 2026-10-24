#!/usr/bin/env python3
"""
数据库迁移脚本：为 note_types 表增加 visible_roles（可见角色）列。
  1. 备份数据库
  2. 为 note_types 表添加 visible_roles 列（TEXT，默认 'admin,editor,viewer'）
  3. 回填已有类型的 visible_roles 为默认值（全部角色可见，向后兼容）
用法:
  python3 migrate_note_visibility.py              # 默认库
  python3 migrate_note_visibility.py /path/to.db  # 指定数据库路径
"""
import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = "data/questions.db"

DEFAULT_VISIBLE_ROLES = "experiencer,viewer,advancer,editor,admin"


def main():
    db_path = DB_PATH
    if not os.path.exists(db_path):
        print("数据库文件不存在: %s" % db_path)
        return

    bak = "%s.bak_%s" % (db_path, datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(db_path, bak)
    print("已备份数据库 -> %s" % bak)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(note_types)")
    cols = [r[1] for r in cur.fetchall()]
    if "visible_roles" not in cols:
        cur.execute(
            "ALTER TABLE note_types ADD COLUMN visible_roles TEXT DEFAULT '%s'"
            % DEFAULT_VISIBLE_ROLES
        )
        print("已添加列: visible_roles")
    else:
        print("列已存在: visible_roles")

    cur.execute(
        "UPDATE note_types SET visible_roles = ? WHERE visible_roles IS NULL OR visible_roles = ''",
        (DEFAULT_VISIBLE_ROLES,),
    )
    backfilled = cur.rowcount
    conn.commit()
    print("已回填 visible_roles 默认值: %d 行" % backfilled)

    cur.execute("SELECT id, type_name, visible_roles FROM note_types ORDER BY id")
    rows = cur.fetchall()
    conn.close()

    print("\n当前 note_types 可见范围：")
    for tid, tname, vroles in rows:
        print("  ID %-3d %-20s 可见: %s" % (tid, tname, vroles or "(空)"))
    print("\n迁移完成")


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            DB_PATH = arg
    main()
