"""录题 Agent 授权服务。

复用 ai_whitelist 表（purpose='record_agent'）存储录题 Agent 授权白名单。

授权层级：
  - admin：自动授权，无需白名单记录，不可被取消
  - editor / advancer：需 admin 手动授权（写入 ai_whitelist purpose='record_agent'）
  - viewer / experiencer：不可被授权

原子性保证：
  grant_record_agent / revoke_record_agent 在同一 sqlite3 事务内完成
  白名单写入 + 日志记录，同时成功或同时回滚。
"""
import sqlite3
from datetime import datetime

from utils.permissions import (
    is_admin,
    can_be_authorized_for_record_agent,
)
from services.log_services import VALID_LOG_ACTIONS

DB_PATH = "data/questions.db"

RECORD_AGENT_PURPOSE = "record_agent"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _insert_log(cur, operator, case_id, action, detail=None, session_id=None):
    """在同一事务内写入操作日志（保证原子性）。

    action 必须在白名单内，否则跳过。detail 为 dict 时 json 序列化。
    """
    if action not in VALID_LOG_ACTIONS:
        return None
    import json
    from datetime import datetime
    detail_str = json.dumps(detail, ensure_ascii=False) if isinstance(detail, dict) else detail
    cur.execute(
        "INSERT INTO operation_logs (operator, case_id, action, detail, created_at, session_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (operator, case_id, action, detail_str, datetime.now().isoformat(), session_id),
    )
    return cur.lastrowid


def _get_user_role(user_id):
    """查询用户角色（未删除）。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE id = ? AND is_deleted = 0", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def is_record_agent_enabled(user_id) -> bool:
    """判断用户是否已授权使用录题 Agent。

    admin 自动 True；否则查 ai_whitelist purpose='record_agent'。
    """
    role = _get_user_role(user_id)
    if role is None:
        return False
    if is_admin(role):
        return True
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM ai_whitelist WHERE user_id = ? AND purpose = ?",
        (user_id, RECORD_AGENT_PURPOSE),
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def grant_record_agent(user_id, added_by):
    """为用户授权使用录题 Agent（原子操作）。

    Args:
        user_id: 待授权用户 ID
        added_by: 授权操作者 ID（应为 admin）

    Returns:
        tuple[bool, str]: (是否成功, 提示消息)
    """
    role = _get_user_role(user_id)
    if role is None:
        return False, "目标用户不存在或已删除"
    if is_admin(role):
        return False, "管理员自动授权，无需重复授权"
    if not can_be_authorized_for_record_agent(role):
        return False, "仅 editor 及以上角色可被授权"

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT OR IGNORE INTO ai_whitelist (user_id, added_at, added_by, purpose) "
            "VALUES (?, ?, ?, ?)",
            (user_id, datetime.now().isoformat(), added_by, RECORD_AGENT_PURPOSE),
        )
        inserted = cur.rowcount > 0
        # 写日志（同一事务，保证原子性）
        _insert_log(
            cur,
            operator="user:%s" % added_by,
            case_id=user_id,
            action="grant_record_agent",
            detail={"target_user_id": user_id, "target_role": role, "inserted": inserted},
            session_id=None,
        )
        conn.commit()
        if inserted:
            return True, "授权成功"
        return True, "该用户已授权，无需重复操作"
    except Exception as e:
        conn.rollback()
        return False, "授权失败: %s" % e
    finally:
        conn.close()


def revoke_record_agent(user_id, revoked_by):
    """取消用户的录题 Agent 授权（原子操作）。

    Args:
        user_id: 待取消授权用户 ID
        revoked_by: 操作者 ID（应为 admin）

    Returns:
        tuple[bool, str]: (是否成功, 提示消息)
    """
    role = _get_user_role(user_id)
    if role is None:
        return False, "目标用户不存在或已删除"
    if is_admin(role):
        return False, "管理员自动授权，不可取消"

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM ai_whitelist WHERE user_id = ? AND purpose = ?",
            (user_id, RECORD_AGENT_PURPOSE),
        )
        deleted = cur.rowcount > 0
        _insert_log(
            cur,
            operator="user:%s" % revoked_by,
            case_id=user_id,
            action="revoke_record_agent",
            detail={"target_user_id": user_id, "target_role": role, "deleted": deleted},
            session_id=None,
        )
        conn.commit()
        if deleted:
            return True, "已取消授权"
        return True, "该用户未授权，无需取消"
    except Exception as e:
        conn.rollback()
        return False, "取消授权失败: %s" % e
    finally:
        conn.close()


def get_record_agent_whitelist():
    """返回已授权录题 Agent 的 user_id 列表（不含 admin）。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id FROM ai_whitelist WHERE purpose = ? ORDER BY user_id",
        (RECORD_AGENT_PURPOSE,),
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]
