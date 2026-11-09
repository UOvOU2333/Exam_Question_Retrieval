"""录题 Agent 会话快照持久化服务。

把 session_state 中的会话状态（草稿、对话、匹配、文件元数据、撤销栈、
权限开关、当前批次）序列化为 JSON 存入 SQLite，支持恢复历史会话。

表结构（幂等创建）：
    record_agent_sessions
        sid         TEXT PRIMARY KEY
        user_id     INTEGER NOT NULL
        title       TEXT
        data        TEXT NOT NULL     会话快照 JSON
        created_at  TEXT NOT NULL
        updated_at  TEXT NOT NULL

文件过期：DeepSeek Files API 文件默认 1 小时过期（FILE_EXPIRE_SECONDS）。
恢复会话时按上传时间与本地 PDF 是否还存在做检测，过期页图/图片清空引用，
由页面提示用户重新上传或重新加载批次。
"""
import json
import os
import sqlite3
from datetime import datetime

from chains.record_agent_files import FILE_EXPIRE_SECONDS, FILE_IDLE_EXPIRE_SECONDS

DB_PATH = "data/questions.db"
# 每个用户保留的历史会话数量上限
MAX_SESSIONS_PER_USER = 50

# 需要随会话保存的 session_state key（%s 为 sid）
SESSION_KEYS = (
    "record_drafts_%s",
    "record_draft_seq_%s",
    "record_undo_%s",
    "record_redo_%s",
    "record_images_%s",
    "record_pdfs_%s",
    "record_fragments_%s",
    "record_fragment_seq_%s",
    "record_matches_%s",
    "record_match_seq_%s",
    "ra_perm_switches_%s",
    "ra_perm_emergency_stop_%s",
)
# 全局（非按 sid）会话状态 key
GLOBAL_KEYS = (
    "ra_history",
    "ra_pdf_local_paths",
    "ra_active_batch",
    "ra_show_preview",
)
# 快照元数据 key，恢复时不写回 session_state
_META_KEYS = {"version", "saved_at", "session_id", "title"}


def _connect(db_path=DB_PATH):
    return sqlite3.connect(db_path, timeout=10)


def _ensure_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS record_agent_sessions (
            sid TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ra_sessions_user ON record_agent_sessions(user_id, updated_at)"
    )


def build_snapshot(state, sid):
    """从 session_state（dict-like）构建快照。"""
    snapshot = {
        "version": 1,
        "saved_at": datetime.now().isoformat(),
        "session_id": sid,
    }
    for key_tpl in SESSION_KEYS:
        key = key_tpl % sid
        value = state.get(key)
        if value is not None:
            snapshot[key] = value
    for key in GLOBAL_KEYS:
        if key in state:
            snapshot[key] = state.get(key)
    return snapshot


def save_session(sid, user_id, title, snapshot, db_path=DB_PATH):
    """保存或更新会话快照，并清理超出上限的旧记录。"""
    conn = _connect(db_path)
    try:
        _ensure_table(conn)
        now = datetime.now().isoformat()
        payload = json.dumps(snapshot, ensure_ascii=False, default=str)
        conn.execute(
            """
            INSERT INTO record_agent_sessions (sid, user_id, title, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(sid) DO UPDATE SET
                title = excluded.title,
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (sid, user_id, title or sid, payload, now, now),
        )
        conn.execute(
            """
            DELETE FROM record_agent_sessions
            WHERE user_id = ? AND sid NOT IN (
                SELECT sid FROM record_agent_sessions
                WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?
            )
            """,
            (user_id, user_id, MAX_SESSIONS_PER_USER),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def list_sessions(user_id, limit=20, db_path=DB_PATH):
    """列出某用户最近的历史会话（含草稿数与对话轮数）。"""
    conn = _connect(db_path)
    try:
        _ensure_table(conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT sid, title, data, created_at, updated_at
            FROM record_agent_sessions
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        drafts = 0
        messages = 0
        try:
            data = json.loads(row["data"] or "{}")
            drafts = len(data.get("record_drafts_%s" % row["sid"], []) or [])
            messages = len(data.get("ra_history", []) or [])
        except (ValueError, TypeError):
            pass
        result.append({
            "sid": row["sid"],
            "title": row["title"] or row["sid"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "drafts": drafts,
            "messages": messages,
        })
    return result


def load_session(sid, user_id, db_path=DB_PATH):
    """读取某会话快照（仅本人可见），不存在返回 None。"""
    conn = _connect(db_path)
    try:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT data FROM record_agent_sessions WHERE sid = ? AND user_id = ?",
            (sid, user_id),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return json.loads(row[0] or "{}")
    except (ValueError, TypeError):
        return None


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _is_idle_expired(item, now):
    """按最后使用时间判断是否超过空闲过期阈值（默认 24 小时）。"""
    last_used = _parse_time(
        item.get("last_used_at") or item.get("added_at")
        or item.get("page_files_uploaded_at")
    )
    if last_used is None:
        return False
    return (now - last_used).total_seconds() > FILE_IDLE_EXPIRE_SECONDS


def _is_hard_expired(uploaded_at, now):
    """远端 Files API 硬过期保护（有效期 30 天，提前 1 小时视为过期）。"""
    uploaded = _parse_time(uploaded_at)
    if uploaded is None:
        return False
    return (now - uploaded).total_seconds() > FILE_EXPIRE_SECONDS - 3600


def check_expired_files(snapshot, now=None):
    """检测快照中文件是否过期，清理失效引用。

    过期规则：
      - 图片：超过 24 小时未使用则移除，需重新上传
      - PDF：本地 PDF 不存在则标记 expired；页图超过 24 小时未使用
        或接近远端硬有效期则清空页图与处理状态，需重新加载批次
      - 手动删除（deleted=True）的文件直接跳过，不提示过期

    注意：恢复会话本身不算“使用”，不刷新 last_used_at；
    只有用户真实操作（加载批次、发送对话使用文件）才由页面刷新时间。

    warnings 只包含文件名，不含“已过期/请重新上传”等动作文案，
    由页面统一提示。

    返回 (snapshot, warnings)。只修改传入的快照副本，不访问网络。
    """
    now = now or datetime.now()
    data = json.loads(json.dumps(snapshot, ensure_ascii=False, default=str))
    warnings = []

    images_key = next((k for k in data if k.startswith("record_images_")), None)
    if images_key:
        kept = []
        for image in data.get(images_key) or []:
            if image.get("deleted"):
                # 手动删除的文件不再提示过期
                kept.append(image)
                continue
            if _is_idle_expired(image, now):
                warnings.append(image.get("filename", ""))
            else:
                kept.append(image)
        data[images_key] = kept

    pdfs_key = next((k for k in data if k.startswith("record_pdfs_")), None)
    local_paths = data.get("ra_pdf_local_paths") or {}
    if pdfs_key:
        for pdf in data.get(pdfs_key) or []:
            if pdf.get("deleted"):
                # 手动删除的文件不再提示过期
                continue
            file_id = pdf.get("file_id")
            local_path = local_paths.get(file_id, "")
            local_ok = bool(local_path) and os.path.exists(local_path)
            if not local_ok:
                pdf["expired"] = True
                pdf["page_file_ids"] = []
                pdf["page_file_map"] = {}
                pdf["active_pages"] = []
                pdf["processed_pages"] = []
                pdf["page_files_uploaded_at"] = None
                local_paths.pop(file_id, None)
                warnings.append(pdf.get("filename", ""))
                continue
            idle_expired = _is_idle_expired(pdf, now)
            hard_expired = _is_hard_expired(pdf.get("page_files_uploaded_at"), now)
            if pdf.get("page_file_ids") and (idle_expired or hard_expired):
                pdf["expired"] = True
                pdf["page_file_ids"] = []
                pdf["page_file_map"] = {}
                pdf["active_pages"] = []
                pdf["processed_pages"] = []
                pdf["page_files_uploaded_at"] = None
                warnings.append(pdf.get("filename", ""))

    data["ra_pdf_local_paths"] = local_paths

    batch = data.get("ra_active_batch")
    if batch:
        pdfs = data.get(pdfs_key) or [] if pdfs_key else []
        pdf = next((p for p in pdfs if p.get("file_id") == batch.get("file_id")), None)
        if not pdf or pdf.get("expired") or not pdf.get("page_file_ids"):
            data.pop("ra_active_batch", None)

    return data, warnings


def apply_snapshot(state, sid, snapshot):
    """把快照写回 session_state（仅会话状态 key，不触碰 widget key）。"""
    for key, value in snapshot.items():
        if key in _META_KEYS:
            continue
        state[key] = value
    state["ra_session_id"] = sid


def restore_session(state, sid, user_id, db_path=DB_PATH):
    """恢复历史会话：读取快照 → 过期检测 → 写回 session_state。

    返回 (snapshot, warnings)；会话不存在返回 (None, [])。
    """
    snapshot = load_session(sid, user_id, db_path=db_path)
    if snapshot is None:
        return None, []
    snapshot, warnings = check_expired_files(snapshot)
    apply_snapshot(state, sid, snapshot)
    return snapshot, warnings