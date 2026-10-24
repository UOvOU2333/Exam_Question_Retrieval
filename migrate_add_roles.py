#!/usr/bin/env python3
"""
数据库迁移脚本：新增 experiencer、advancer 角色后，回填 note_types.visible_roles。
  1. 备份数据库
  2. 将 visible_roles 为 NULL/空/旧默认值(admin,editor,viewer) 的行更新为新默认值
  3. 自定义 visible_roles 保持不变（管理员后续手动调整新角色可见性）
用法:
  python3 migrate_add_roles.py              # 默认库
  python3 migrate_add_roles.py /path/to.db  # 指定数据库路径
"""
import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = "data/questions.db"

OLD_DEFAULT = "admin,editor,viewer"
NEW_DEFAULT = "experiencer,viewer,advancer,editor,admin"


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

    cur.execute(
        "UPDATE note_types SET visible_roles = ? "
        "WHERE visible_roles IS NULL OR visible_roles = '' OR visible_roles = ?",
        (NEW_DEFAULT, OLD_DEFAULT),
    )
    updated = cur.rowcount
    conn.commit()
    print("已回填 visible_roles 为新默认值: %d 行" % updated)

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
