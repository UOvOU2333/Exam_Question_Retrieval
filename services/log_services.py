"""操作日志服务（录题 Agent 全量留痕）。

设计要点：
  - 原生 sqlite3 实现，与主项目一致，不引入 SQLAlchemy
  - operation_logs 表仅追加（INSERT），无 UPDATE/DELETE 接口，保证日志不可篡改
  - action 必须在白名单 VALID_LOG_ACTIONS 内，否则拒绝写入
  - detail 支持 dict 或 str，dict 自动 json.dumps
  - operator 格式为用户名或 `agent:<user_id>`
  - 按 session_id 查询返回时间倒序列表

表结构（由 migrate_record_agent.py 创建）：
    id           INTEGER PRIMARY KEY AUTOINCREMENT
    operator     TEXT
    case_id      INTEGER
    action       TEXT NOT NULL
    detail       TEXT
    created_at   TEXT NOT NULL
    session_id   TEXT
"""
import sqlite3
import json
from datetime import datetime

DB_PATH = "data/questions.db"

# 操作日志动作白名单（spec 6.3 全部 17 种动作）
VALID_LOG_ACTIONS = {
    "tool_call",
    "draft_create",
    "draft_discard",
    "commit",
    "undo",
    "redo",
    "grant_record_agent",
    "revoke_record_agent",
    "permission_denied",
    "permission_toggle",
    "pdf_upload",
    "pdf_parse",
    "pdf_split",
    "pdf_parse_degrade",
    "rubric_partition",
    "rubric_split",
    "rubric_match",
    "rubric_match_revise",
    "rubric_match_resolve",
    "rubric_upload",
}


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _ensure_operation_logs_table():
    """幂等建表（兼容迁移脚本未执行的场景）。"""
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS operation_logs (
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
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_operation_logs_session ON operation_logs(session_id)"
    )
    conn.commit()
    conn.close()


def record_log(operator, case_id, action, detail=None, session_id=None):
    """写入一条操作日志。

    Args:
        operator: 操作者，用户名或 `agent:<user_id>`
        case_id: 关联题目 ID（可 None）
        action: 动作类型，必须在 VALID_LOG_ACTIONS 内
        detail: 详情，dict 或 str（dict 自动 json.dumps）
        session_id: 会话 ID（可 None）

    Returns:
        int | None: 日志 ID；action 非法或写入失败返回 None
    """
    if action not in VALID_LOG_ACTIONS:
        return None
    _ensure_operation_logs_table()
    if isinstance(detail, dict):
        detail_str = json.dumps(detail, ensure_ascii=False)
    else:
        detail_str = detail
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO operation_logs (operator, case_id, action, detail, created_at, session_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                operator,
                case_id,
                action,
                detail_str,
                datetime.now().isoformat(),
                session_id,
            ),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        print("写入操作日志失败: %s" % e)
        return None
    finally:
        conn.close()


def get_session_logs(session_id, limit=100):
    """按会话 ID 查询日志，时间倒序。"""
    _ensure_operation_logs_table()
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, operator, case_id, action, detail, created_at, session_id
        FROM operation_logs
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_logs(limit=50):
    """全局最近日志，时间倒序。"""
    _ensure_operation_logs_table()
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, operator, case_id, action, detail, created_at, session_id
        FROM operation_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
