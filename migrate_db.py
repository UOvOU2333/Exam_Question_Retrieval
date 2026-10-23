#!/usr/bin/env python3
"""
数据库迁移脚本（自包含，无需项目其他模块）：
  1. 备份数据库
  2. 为 questions 表添加 question_type / knowledge_modules 列
  3. 批量自动检测并回填题型（无法判定的留空待人工）
用法:
  python3 migrate_db.py              # 仅回填题型为空的题目
  python3 migrate_db.py --force      # 重新检测所有题目（覆盖已有值）
  python3 migrate_db.py /path/to.db  # 指定数据库路径
"""
import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = "data/questions.db"


def detect_question_type(content, answer, question_no=None):
    """自动检测题型：选择题 / 非选择题 / 判断题 / None"""
    if answer is None:
        answer = ""
    a = answer.strip()

    # 判断题：答案为 T/F（不区分大小写）
    if a.upper() in ("T", "F"):
        return "判断题"
    # 答案为纯字母组合（A-D，≤4字符）→ 选择题
    if a and len(a) <= 4 and all(c in "ABCDabcd" for c in a):
        return "选择题"
    # 答案较长 → 非选择题
    if len(a) > 10:
        return "非选择题"
    # 题号为中文数字 → 非选择题
    if question_no and question_no.strip() in ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十"):
        return "非选择题"
    # 题首"阅读材料" → 非选择题
    if content and content.strip().startswith("阅读材料"):
        return "非选择题"
    # 答案含换行/评分表/"分" → 非选择题
    if a and ("\n" in a or "|" in a or "分" in a):
        return "非选择题"
    return None


def main(force=False):
    db_path = DB_PATH
    if not os.path.exists(db_path):
        print("数据库文件不存在: %s" % db_path)
        return

    # 1. 备份
    bak = "%s.bak_%s" % (db_path, datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(db_path, bak)
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

    stats = {"选择题": 0, "非选择题": 0, "判断题": 0, "跳过": 0}
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

    print("\n批量回填完成：选择题 %d / 非选择题 %d / 判断题 %d / 待人工 %d"
          % (stats["选择题"], stats["非选择题"], stats["判断题"], stats["跳过"]))
    print("\n当前题型分布：")
    for qt, cnt in dist:
        print("  %-8s %d 题" % (qt or "(空)", cnt))
    print("\n迁移全部完成")


if __name__ == "__main__":
    import sys
    force = False
    for arg in sys.argv[1:]:
        if arg == "--force":
            force = True
        elif not arg.startswith("-"):
            DB_PATH = arg
    main(force=force)
