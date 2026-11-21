# services/knowledge_base_services.py
"""知识库服务层：分组、条目、条目-题目关联、预设颜色的 CRUD。

沿用项目裸 sqlite3 风格（见 note_services.py），统一软删 + 审计字段。
管理类操作在服务层做权限兜底（operator_role 校验 kb_manage）。
"""
import sqlite3

from utils.permissions import has_permission, is_admin

DB_PATH = "data/questions.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# ===================== 分组 =====================

def create_group(name, parent_id, created_by, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return None
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO kb_groups (name, parent_id, created_by) VALUES (?, ?, ?)",
            (name, parent_id, created_by),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        print(f"创建分组失败: {e}")
        return None
    finally:
        conn.close()


def update_group(group_id, name=None, parent_id=None, sort_order=None, updated_by=None, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return False
    if parent_id == group_id:
        return False
    fields, params = [], []
    if name is not None:
        fields.append("name = ?")
        params.append(name)
    if parent_id is not None:
        fields.append("parent_id = ?")
        params.append(parent_id)
    if sort_order is not None:
        fields.append("sort_order = ?")
        params.append(sort_order)
    if not fields:
        return False
    fields.append("updated_by = ?")
    params.append(updated_by)
    fields.append("updated_at = datetime('now','localtime')")
    params.append(group_id)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE kb_groups SET {', '.join(fields)} WHERE id = ? AND is_deleted = 0", params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def soft_delete_group(group_id, updated_by, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE kb_groups SET is_deleted=1, updated_by=?, updated_at=datetime('now','localtime') "
            "WHERE id=? AND is_deleted=0",
            (updated_by, group_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def restore_group(group_id, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE kb_groups SET is_deleted=0 WHERE id=?", (group_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_all_groups(include_deleted=False):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cond = "" if include_deleted else "WHERE is_deleted = 0"
    cur.execute(f"SELECT * FROM kb_groups {cond} ORDER BY sort_order, id")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_group_path(group_id):
    """返回从根到该分组的路径列表（含自身），用于面包屑展示。"""
    path = []
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    gid = group_id
    seen = set()
    while gid and gid not in seen:
        seen.add(gid)
        cur.execute("SELECT id, name, parent_id FROM kb_groups WHERE id=?", (gid,))
        r = cur.fetchone()
        if not r:
            break
        path.append(dict(r))
        gid = r["parent_id"]
    conn.close()
    return list(reversed(path))


# ===================== 条目 =====================

def create_entry(title, content, color, group_id, created_by, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return None
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO kb_entries (title, content, color, group_id, created_by) VALUES (?, ?, ?, ?, ?)",
            (title, content or "", color or "#409EFF", group_id, created_by),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        print(f"创建条目失败: {e}")
        return None
    finally:
        conn.close()


def update_entry(entry_id, title=None, content=None, color=None, group_id=None,
                 updated_by=None, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return False
    fields, params = [], []
    if title is not None:
        fields.append("title = ?")
        params.append(title)
    if content is not None:
        fields.append("content = ?")
        params.append(content)
    if color is not None:
        fields.append("color = ?")
        params.append(color)
    if group_id is not None:
        fields.append("group_id = ?")
        params.append(group_id)
    if not fields:
        return False
    fields.append("updated_by = ?")
    params.append(updated_by)
    fields.append("updated_at = datetime('now','localtime')")
    params.append(entry_id)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE kb_entries SET {', '.join(fields)} WHERE id=? AND is_deleted=0", params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def soft_delete_entry(entry_id, updated_by, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE kb_entries SET is_deleted=1, updated_by=?, updated_at=datetime('now','localtime') "
            "WHERE id=? AND is_deleted=0",
            (updated_by, entry_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def restore_entry(entry_id, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE kb_entries SET is_deleted=0 WHERE id=?", (entry_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_entry(entry_id):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM kb_entries WHERE id=? AND is_deleted=0", (entry_id,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def get_all_entries(group_id=None, include_deleted=False):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    conds = []
    params = []
    if not include_deleted:
        conds.append("is_deleted = 0")
    if group_id is not None:
        conds.append("group_id = ?")
        params.append(group_id)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    cur.execute(f"SELECT * FROM kb_entries {where} ORDER BY id DESC", params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_entries(keyword=None, group_ids=None, color=None, include_deleted=False):
    """按关键词/分组/颜色检索条目，附带关联题目数。

    :param group_ids: 分组 ID 列表，传多个时取并集（任一匹配即纳入）；None/空表示不限分组
    """
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    conds = []
    params = []
    if not include_deleted:
        conds.append("e.is_deleted = 0")
    if keyword:
        conds.append("(e.title LIKE ? OR e.content LIKE ?)")
        params += [f"%{keyword}%", f"%{keyword}%"]
    if group_ids:
        placeholders = ",".join("?" * len(group_ids))
        conds.append(f"e.group_id IN ({placeholders})")
        params.extend(group_ids)
    if color:
        conds.append("e.color = ?")
        params.append(color)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    cur.execute(
        f"""SELECT e.*, g.name AS group_name,
            (SELECT COUNT(*) FROM kb_entry_questions eq WHERE eq.entry_id = e.id) AS question_count
            FROM kb_entries e
            LEFT JOIN kb_groups g ON e.group_id = g.id
            {where}
            ORDER BY e.id DESC""",
        params,
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===================== 条目-题目 关联 =====================

def add_question_to_entry(entry_id, question_id, created_by, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT OR IGNORE INTO kb_entry_questions (entry_id, question_id, created_by) VALUES (?, ?, ?)",
            (entry_id, question_id, created_by),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"添加关联失败: {e}")
        return False
    finally:
        conn.close()


def remove_question_from_entry(entry_id, question_id, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM kb_entry_questions WHERE entry_id=? AND question_id=?",
            (entry_id, question_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_question_entries(question_id, entry_ids, created_by, operator_role=None):
    """批量替换某题的关联条目集合（差量增删）。"""
    if not has_permission(operator_role, "kb_manage"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT entry_id FROM kb_entry_questions WHERE question_id=?", (question_id,))
        current = {r[0] for r in cur.fetchall()}
        target = set(entry_ids)
        for eid in target - current:
            cur.execute(
                "INSERT OR IGNORE INTO kb_entry_questions (entry_id, question_id, created_by) VALUES (?, ?, ?)",
                (eid, question_id, created_by),
            )
        for eid in current - target:
            cur.execute(
                "DELETE FROM kb_entry_questions WHERE entry_id=? AND question_id=?",
                (eid, question_id),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def get_entry_questions(entry_id):
    """返回条目关联的题目摘要列表（含原文，供详情页展开）。"""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """SELECT q.questionID, q.year, q.paper_type, q.question_no, q.question_type,
                  q.content, q.answer, q.analysis, q.source, q.knowledge_modules,
                  q.isInRecycleBin
           FROM kb_entry_questions eq
           JOIN questions q ON eq.question_id = q.questionID
           WHERE eq.entry_id = ?
           ORDER BY q.year DESC, q.question_no""",
        (entry_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_question_entries(question_id):
    """返回某题关联的知识库条目列表（含颜色，供胶囊展示）。"""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """SELECT e.id, e.title, e.color, e.group_id, g.name AS group_name
           FROM kb_entry_questions eq
           JOIN kb_entries e ON eq.entry_id = e.id
           LEFT JOIN kb_groups g ON e.group_id = g.id
           WHERE eq.question_id = ? AND e.is_deleted = 0
           ORDER BY e.id""",
        (question_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===================== 预设颜色 =====================

def get_all_preset_colors():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM kb_preset_colors ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_preset_color(name, value, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO kb_preset_colors (color_name, color_value) VALUES (?, ?)", (name, value))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_preset_color(color_id, operator_role=None):
    if not has_permission(operator_role, "kb_manage"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM kb_preset_colors WHERE id=?", (color_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
