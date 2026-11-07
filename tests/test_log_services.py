"""操作日志服务单元测试。"""
import os
import tempfile
import sqlite3

# 使用临时数据库避免污染
_tmp = tempfile.mkdtemp()
os.environ.setdefault("TEST_DB", os.path.join(_tmp, "test_log.db"))


def _setup_db():
    db = os.path.join(_tmp, "test_log.db")
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT, case_id INTEGER, action TEXT NOT NULL,
            detail TEXT, created_at TEXT NOT NULL, session_id TEXT
        )
    """)
    conn.commit()
    conn.close()


def test_valid_actions():
    """17 种动作均能写入。"""
    _setup_db()
    import services.log_services as ls
    ls.DB_PATH = os.path.join(_tmp, "test_log.db")
    actions = [
        "tool_call", "draft_create", "draft_discard", "commit", "undo", "redo",
        "grant_record_agent", "revoke_record_agent", "permission_denied",
        "pdf_upload", "pdf_parse", "pdf_split", "pdf_parse_degrade",
        "rubric_partition", "rubric_split", "rubric_match", "rubric_match_revise",
        "rubric_upload",
    ]
    for a in actions:
        lid = ls.record_log(operator="test", case_id=1, action=a, detail={"k": "v"}, session_id="s1")
        assert lid is not None, "动作 %s 写入失败" % a


def test_invalid_action_rejected():
    """非白名单 action 拒绝写入。"""
    _setup_db()
    import services.log_services as ls
    ls.DB_PATH = os.path.join(_tmp, "test_log.db")
    lid = ls.record_log(operator="test", case_id=1, action="evil_action", session_id="s1")
    assert lid is None


def test_session_logs_order():
    """按 session_id 查询返回倒序。"""
    _setup_db()
    import services.log_services as ls
    ls.DB_PATH = os.path.join(_tmp, "test_log.db")
    ls.record_log(operator="test", case_id=1, action="commit", session_id="s2")
    ls.record_log(operator="test", case_id=2, action="undo", session_id="s2")
    logs = ls.get_session_logs("s2")
    assert len(logs) == 2
    # 倒序：undo 在前
    assert logs[0]["action"] == "undo"
