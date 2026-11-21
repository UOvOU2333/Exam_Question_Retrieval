# migrate_knowledge_base.py
"""知识库功能建表迁移（幂等）。

新增 4 张表：
    kb_groups            知识库分组（父子树，支持多层）
    kb_entries           知识库条目（标题+富文本正文+颜色+分组归属）
    kb_entry_questions   条目与题目的多对多关联
    kb_preset_colors     预设色板

用法：
    python3 migrate_knowledge_base.py            # 建表 + 初始化预设颜色
    python3 migrate_knowledge_base.py --dry-run  # 只打印不执行
"""
import argparse
import sqlite3
import sys

DB_PATH = "data/questions.db"

# 预设色板（参考 TaskScheduler，覆盖常见语义色）
DEFAULT_COLORS = [
    ("默认蓝", "#409EFF"),
    ("成功绿", "#67C23A"),
    ("警告橙", "#E6A23C"),
    ("危险红", "#F56C6C"),
    ("信息灰", "#909399"),
    ("紫色",   "#9B59B6"),
    ("青色",   "#13C2C2"),
    ("粉色",   "#EB2F96"),
    ("靛蓝",   "#3F51B5"),
    ("棕色",   "#8D6E63"),
]


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def table_exists(cur, name):
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def create_tables(conn, dry_run=False):
    cur = conn.cursor()
    statements = [
        # 分组：父子树多层
        """CREATE TABLE IF NOT EXISTS kb_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            sort_order INTEGER DEFAULT 0,
            created_by INTEGER,
            updated_by INTEGER,
            created_at DATETIME DEFAULT (datetime('now','localtime')),
            updated_at DATETIME,
            is_deleted INTEGER DEFAULT 0,
            FOREIGN KEY (parent_id) REFERENCES kb_groups(id)
        )""",
        # 条目：标签+详情
        """CREATE TABLE IF NOT EXISTS kb_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            color TEXT DEFAULT '#409EFF',
            group_id INTEGER,
            created_by INTEGER,
            updated_by INTEGER,
            created_at DATETIME DEFAULT (datetime('now','localtime')),
            updated_at DATETIME,
            is_deleted INTEGER DEFAULT 0,
            FOREIGN KEY (group_id) REFERENCES kb_groups(id)
        )""",
        # 条目-题目 多对多关联
        """CREATE TABLE IF NOT EXISTS kb_entry_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            created_by INTEGER,
            created_at DATETIME DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (entry_id) REFERENCES kb_entries(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions(questionID) ON DELETE CASCADE,
            UNIQUE(entry_id, question_id)
        )""",
        # 预设色板
        """CREATE TABLE IF NOT EXISTS kb_preset_colors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            color_name TEXT NOT NULL UNIQUE,
            color_value TEXT NOT NULL
        )""",
        # 索引
        "CREATE INDEX IF NOT EXISTS idx_kb_groups_parent ON kb_groups(parent_id)",
        "CREATE INDEX IF NOT EXISTS idx_kb_entries_group ON kb_entries(group_id)",
        "CREATE INDEX IF NOT EXISTS idx_kb_entry_questions_entry ON kb_entry_questions(entry_id)",
        "CREATE INDEX IF NOT EXISTS idx_kb_entry_questions_question ON kb_entry_questions(question_id)",
    ]

    for sql in statements:
        if dry_run:
            print("[DRY-RUN]", sql.strip().split("\n")[0])
        else:
            cur.execute(sql)

    if not dry_run:
        # 初始化预设颜色（跳过已存在的）
        for name, value in DEFAULT_COLORS:
            try:
                cur.execute(
                    "INSERT OR IGNORE INTO kb_preset_colors (color_name, color_value) VALUES (?, ?)",
                    (name, value),
                )
            except sqlite3.IntegrityError:
                pass
        conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = get_conn()
    try:
        create_tables(conn, dry_run=args.dry_run)
    finally:
        conn.close()

    if args.dry_run:
        print("DRY-RUN 完成，未实际建表")
        return

    # 验证
    conn = get_conn()
    cur = conn.cursor()
    for t in ("kb_groups", "kb_entries", "kb_entry_questions", "kb_preset_colors"):
        if not table_exists(cur, t):
            print(f"[失败] 表 {t} 未创建", file=sys.stderr)
            sys.exit(1)
    cur.execute("SELECT COUNT(*) FROM kb_preset_colors")
    n = cur.fetchone()[0]
    conn.close()
    print(f"知识库表创建成功，预设颜色 {n} 条")


if __name__ == "__main__":
    main()
