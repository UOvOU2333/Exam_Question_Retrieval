#!/usr/bin/env python3
"""
数据库迁移脚本（复用项目统一题型规则）：
  1. 备份数据库
  2. 为 questions 表添加 question_type / knowledge_modules 列
  3. 批量自动检测并回填题型（无法判定的留空待人工）
用法:
  python3 migrate_db.py              # 仅回填题型为空的题目
  python3 migrate_db.py --rename-types-only  # 仅改名旧题型，不重新识别
  python3 migrate_db.py --force      # 重新检测所有题目（覆盖已有值）
  python3 migrate_db.py /path/to.db  # 指定数据库路径
"""
import sqlite3
import os
from datetime import datetime
from contextlib import closing

DB_PATH = "data/questions.db"


from tools.exam_type_utils import QUESTION_TYPES, detect_question_type


def main(force=False, rename_types_only=False):
    db_path = DB_PATH
    if not os.path.exists(db_path):
        print("数据库文件不存在: %s" % db_path)
        return

    # 1. 备份
    bak = "%s.bak_%s" % (db_path, datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(bak)) as target:
        source.backup(target)
    print("已备份数据库 -> %s" % bak)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 2. 添加列
    cur.execute("PRAGMA table_info(questions)")
    cols = [r[1] for r in cur.fetchall()]
    for col_name in ("question_type", "knowledge_modules"):
        if col_name not in cols:
            cur.execute("ALTER TABLE questions ADD COLUMN %s TEXT" % col_name)
            print("已添加列: %s" % col_name)
        else:
            print("列已存在: %s" % col_name)
    conn.commit()

    # 精确改名，包含回收站；不覆盖其他已有人工作出的分类。
    cur.execute(
        "UPDATE questions SET question_type = ? WHERE question_type = ?",
        ("单项选择题", "选择题"),
    )
    print("已将 %d 道题的选择题改名为单项选择题" % cur.rowcount)
    conn.commit()
    if rename_types_only:
        conn.close()
        print("题型改名完成，未重新识别题目")
        return

    # 3. 批量回填题型
    if force:
        cur.execute(
            "SELECT questionID, content, answer, question_no, question_type "
            "FROM questions WHERE isInRecycleBin = 0"
        )
        print("模式: --force（重新检测所有题目）")
    else:
        cur.execute(
            "SELECT questionID, content, answer, question_no, question_type "
            "FROM questions WHERE isInRecycleBin = 0 "
            "AND (question_type IS NULL OR question_type = '')"
        )
        print("模式: 仅回填题型为空的题目")
    rows = cur.fetchall()

    stats = {qtype: 0 for qtype in QUESTION_TYPES}
    stats["跳过"] = 0
    for qid, content, answer, qno, _ in rows:
        qtype = detect_question_type(content, answer, qno)
        if qtype:
            cur.execute(
                "UPDATE questions SET question_type = ? WHERE questionID = ?",
                (qtype, qid),
            )
            stats[qtype] += 1
        else:
            stats["跳过"] += 1
    conn.commit()

    # 4. 验证并输出分布
    cur.execute(
        "SELECT question_type, COUNT(*) FROM questions "
        "WHERE isInRecycleBin = 0 GROUP BY question_type"
    )
    dist = cur.fetchall()
    conn.close()

    print("\n批量回填完成：" + " / ".join(f"{name} {count}" for name, count in stats.items()))
    print("\n当前题型分布：")
    for qt, cnt in dist:
        print("  %-8s %d 题" % (qt or "(空)", cnt))
    print("\n迁移全部完成")


if __name__ == "__main__":
    import sys
    force = False
    rename_types_only = False
    for arg in sys.argv[1:]:
        if arg == "--force":
            force = True
        elif arg == "--rename-types-only":
            rename_types_only = True
        elif not arg.startswith("-"):
            DB_PATH = arg
    main(force=force, rename_types_only=rename_types_only)
