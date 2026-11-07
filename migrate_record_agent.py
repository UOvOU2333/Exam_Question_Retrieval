#!/usr/bin/env python3
"""
录题 Agent 数据库迁移脚本（一次性幂等迁移）。

迁移内容：
  1. 备份数据库 data/questions.db 到带时间戳的 .bak 文件
  2. 为 ai_whitelist 表增加 purpose 列（TEXT DEFAULT 'ai_chat'），已存在则跳过
  3. 回填现有 ai_whitelist 记录 purpose='ai_chat'（NULL → 'ai_chat'）
  4. 创建 operation_logs 表（id/operator/case_id/action/detail/created_at/session_id），已存在则跳过
  5. 创建索引 idx_operation_logs_session on operation_logs(session_id)

用法：
  python3 migrate_record_agent.py              # 默认库 data/questions.db
  python3 migrate_record_agent.py /path/to.db  # 指定数据库路径

回滚预案（迁移失败时）：
  1. 用备份文件恢复：cp data/questions.db.bak_YYYYMMDD_HHMMSS data/questions.db
  2. ai_whitelist 表的 purpose 列删除不影响现有功能（默认回退为通用 AI 白名单）
  3. operation_logs 表为新建，删除该表不影响现有功能：DROP TABLE operation_logs
  4. 重新执行 python3 migrate_record_agent.py（幂等）
"""
import sqlite3
import os
from datetime import datetime
from contextlib import closing

DB_PATH = "data/questions.db"


def _column_exists(cur, table, column):
    """判断某表是否存在指定列（基于 PRAGMA table_info）。"""
    cur.execute("PRAGMA table_info(%s)" % table)
    return any(row[1] == column for row in cur.fetchall())


def _table_exists(cur, table):
    """判断某表是否存在。"""
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def _index_exists(cur, index_name):
    """判断某索引是否存在。"""
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    )
    return cur.fetchone() is not None


def main(db_path=None):
    global DB_PATH
    if db_path:
        DB_PATH = db_path
    if not os.path.exists(DB_PATH):
        print("数据库文件不存在: %s" % DB_PATH)
        return False

    # 1. 备份数据库
    bak = "%s.bak_%s" % (DB_PATH, datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    with closing(sqlite3.connect(DB_PATH)) as source, closing(sqlite3.connect(bak)) as target:
        source.backup(target)
    print("已备份数据库 -> %s" % bak)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        # 2. ai_whitelist 表加 purpose 列
        if _table_exists(cur, "ai_whitelist"):
            if not _column_exists(cur, "ai_whitelist", "purpose"):
                cur.execute(
                    "ALTER TABLE ai_whitelist ADD COLUMN purpose TEXT DEFAULT 'ai_chat'"
                )
                print("已为 ai_whitelist 表添加 purpose 列")
            else:
                print("ai_whitelist.purpose 列已存在，跳过")

            # 3. 回填 NULL purpose 为 'ai_chat'
            cur.execute(
                "UPDATE ai_whitelist SET purpose='ai_chat' WHERE purpose IS NULL"
            )
            backfilled = cur.rowcount
            if backfilled > 0:
                print("已回填 %d 条 ai_whitelist 记录 purpose='ai_chat'" % backfilled)
        else:
            print("ai_whitelist 表不存在，跳过 purpose 列迁移（首次建表时由 user_services 处理）")

        # 4. 创建 operation_logs 表
        if not _table_exists(cur, "operation_logs"):
            cur.execute(
                """
                CREATE TABLE operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operator TEXT,
                    case_id INTEGER,
                    action TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL,
                    session_id TEXT
                )
                """
            )
            print("已创建 operation_logs 表")
        else:
            print("operation_logs 表已存在，跳过")

        # 5. 创建索引 idx_operation_logs_session
        if not _index_exists(cur, "idx_operation_logs_session"):
            cur.execute(
                "CREATE INDEX idx_operation_logs_session ON operation_logs(session_id)"
            )
            print("已创建索引 idx_operation_logs_session")
        else:
            print("索引 idx_operation_logs_session 已存在，跳过")

        conn.commit()
        print("\n迁移全部完成")
        return True
    except Exception as e:
        conn.rollback()
        print("\n迁移失败，已回滚事务: %s" % e)
        print("如需恢复，请使用备份文件: %s" % bak)
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    custom_path = None
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            custom_path = arg
    ok = main(db_path=custom_path)
    sys.exit(0 if ok else 1)
