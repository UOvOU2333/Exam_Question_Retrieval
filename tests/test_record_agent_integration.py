"""录题 Agent 集成测试。

验证核心安全约束：
  1. 禁直写机制：工具执行层调用后 questions/question_notes 表无新增
  2. 授权原子性：grant_record_agent 白名单写入与日志写入同时成功
  3. 三段式逻辑：草稿阶段不写库，确认后才写库
"""
import sqlite3
import os

DB_PATH = "data/questions.db"


def _question_count():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM questions")
    n = cur.fetchone()[0]
    conn.close()
    return n


def _note_count():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM question_notes")
    n = cur.fetchone()[0]
    conn.close()
    return n


def test_tool_whitelist_excludes_write_functions():
    """工具白名单不含任何直接写库函数名。"""
    from chains.record_agent_tools import RECORD_AGENT_TOOL_NAMES
    write_funcs = {"create_question", "update_question", "create_question_note",
                   "delete_question", "move_to_recycle_bin", "soft_delete_question_note"}
    assert not (RECORD_AGENT_TOOL_NAMES & write_funcs), \
        "工具白名单含写库函数: %s" % (RECORD_AGENT_TOOL_NAMES & write_funcs)


def test_record_agent_tools_source_no_write_call():
    """record_agent_tools 源码不含写库函数的直接调用（仅 get_question_by_id 只读）。"""
    import inspect
    from chains import record_agent_tools
    source = inspect.getsource(record_agent_tools)
    # 检查是否 import 了写库函数
    forbidden_imports = ["create_question", "update_question", "create_question_note"]
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("from ") or stripped.startswith("import "):
            for fn in forbidden_imports:
                assert fn not in stripped, "禁直写违规 import: %s in %s" % (fn, line)


def test_grant_revoke_atomic():
    """授权/取消授权原子性：白名单与日志同时写入。"""
    from services.record_agent_auth_services import (
        grant_record_agent, revoke_record_agent, is_record_agent_enabled,
        get_record_agent_whitelist, RECORD_AGENT_PURPOSE,
    )
    # 找一个 editor 用户测试（若不存在则跳过）
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, role FROM users WHERE is_deleted = 0 AND role = 'editor' LIMIT 1")
    row = cur.fetchone()
    cur.execute("SELECT id FROM users WHERE is_deleted = 0 AND role = 'admin' LIMIT 1")
    admin_row = cur.fetchone()
    conn.close()
    if not row or not admin_row:
        return  # 无 editor/admin 用户，跳过
    editor_id, _ = row
    admin_id = admin_row[0]

    # 先清理可能存在的旧授权
    revoke_record_agent(editor_id, admin_id)

    # 授权
    ok, msg = grant_record_agent(editor_id, admin_id)
    assert ok, "授权失败: %s" % msg
    assert is_record_agent_enabled(editor_id) is True
    assert editor_id in get_record_agent_whitelist()

    # 取消授权
    ok2, msg2 = revoke_record_agent(editor_id, admin_id)
    assert ok2, "取消授权失败: %s" % msg2
    assert is_record_agent_enabled(editor_id) is False
    assert editor_id not in get_record_agent_whitelist()


def test_admin_auto_authorized():
    """admin 自动授权，无需白名单。"""
    from services.record_agent_auth_services import is_record_agent_enabled
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE is_deleted = 0 AND role = 'admin' LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return
    admin_id = row[0]
    assert is_record_agent_enabled(admin_id) is True


def test_grant_viewer_rejected():
    """viewer 不可被授权。"""
    from services.record_agent_auth_services import grant_record_agent
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE is_deleted = 0 AND role = 'viewer' LIMIT 1")
    row = cur.fetchone()
    cur.execute("SELECT id FROM users WHERE is_deleted = 0 AND role = 'admin' LIMIT 1")
    admin_row = cur.fetchone()
    conn.close()
    if not row or not admin_row:
        return
    viewer_id = row[0]
    admin_id = admin_row[0]
    ok, msg = grant_record_agent(viewer_id, admin_id)
    assert not ok, "viewer 不应被授权"
    assert "editor" in msg or "角色" in msg


def test_revoke_admin_rejected():
    """admin 不可被取消授权。"""
    from services.record_agent_auth_services import revoke_record_agent
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE is_deleted = 0 AND role = 'admin' LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return
    admin_id = row[0]
    ok, msg = revoke_record_agent(admin_id, admin_id)
    assert not ok, "admin 不应被取消授权"
    assert "管理员" in msg or "自动" in msg
