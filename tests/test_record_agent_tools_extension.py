"""录题 Agent 工具层扩展单测（_parse_target_ref / add_note_to_draft / 消歧校验）。"""
from unittest import mock

import pytest

from chains.record_agent_tools import (
    _parse_target_ref,
    _execute_add_note_to_draft,
    _execute_update_question_draft,
    _execute_add_note_draft,
    _execute_record_tool,
    RecordToolContext,
)


# ========== _parse_target_ref ==========

@pytest.mark.parametrize("value,expected", [
    ("draft-1", ("draft", 1)),
    ("draft-99", ("draft", 99)),
    ("草稿一", ("draft", 1)),
    ("草稿1", ("draft", 1)),
    ("草稿十", ("draft", 10)),
    ("第3份草稿", ("draft", 3)),
    ("第三份草稿", ("draft", 3)),
    (5, ("question", 5)),
    ("5", ("question", 5)),
    ("abc", ("ambiguous", "abc")),
    (None, ("ambiguous", None)),
])
def test_parse_target_ref(value, expected):
    assert _parse_target_ref(value) == expected


# ========== 测试基础设施 ==========

class FakeDraftStore:
    def __init__(self, drafts=None):
        self.drafts = drafts or {}

    def get(self, draft_id):
        return self.drafts.get(draft_id)

    def update_snapshot(self, draft_id, updates):
        d = self.drafts.get(draft_id)
        if d is not None:
            d.setdefault("snapshot_after", {}).update(updates)


def make_ctx(draft_store, user_id=1, session_id="s1"):
    return RecordToolContext(
        user_id=user_id, user_role="advancer", session_id=session_id,
        draft_store=draft_store, undo_stack=None, image_gallery=None,
        pdf_library=None, fragment_store=None, match_store=None,
    )


def _make_draft(draft_id, draft_type="create_question", status="pending",
                snapshot_after=None, target_question_id=None):
    return {
        "draft_id": draft_id,
        "draft_type": draft_type,
        "status": status,
        "snapshot_after": snapshot_after or {"content": "题目"},
        "target_question_id": target_question_id,
    }


# ========== _execute_add_note_to_draft 成功路径 ==========

def test_add_note_to_draft_success():
    ds = FakeDraftStore({"draft-1": _make_draft("draft-1", "create_question")})
    ctx = make_ctx(ds)
    with mock.patch("chains.record_agent_tools.get_note_type_by_name",
                    return_value={"id": 3, "type_name": "评分细则"}), \
         mock.patch("chains.record_agent_tools.record_log"):
        result = _execute_add_note_to_draft(
            {"target_draft_id": "draft-1", "type_name": "评分细则", "content": "细则内容"}, ctx)
    assert "已为草稿 draft-1 添加备注" in result
    notes = ds.get("draft-1")["snapshot_after"]["notes"]
    assert len(notes) == 1
    assert notes[0]["type_id"] == 3
    assert notes[0]["content"] == "细则内容"


def test_add_note_to_draft_appends_to_existing_notes():
    ds = FakeDraftStore({"draft-2": _make_draft(
        "draft-2", "update_question",
        snapshot_after={"content": "题", "notes": [{"type_id": 1, "type_name": "旧", "content": "旧备注"}]})})
    ctx = make_ctx(ds)
    with mock.patch("chains.record_agent_tools.get_note_type_by_name",
                    return_value={"id": 3, "type_name": "评分细则"}), \
         mock.patch("chains.record_agent_tools.record_log"):
        result = _execute_add_note_to_draft(
            {"target_draft_id": "draft-2", "type_name": "评分细则", "content": "新备注"}, ctx)
    assert "已为草稿 draft-2" in result
    notes = ds.get("draft-2")["snapshot_after"]["notes"]
    assert len(notes) == 2
    assert notes[1]["content"] == "新备注"


# ========== _execute_add_note_to_draft 失败路径 ==========

def test_add_note_to_draft_missing_fields():
    ctx = make_ctx(FakeDraftStore())
    result = _execute_add_note_to_draft({"target_draft_id": "draft-1"}, ctx)
    assert "缺少必填字段" in result


def test_add_note_to_draft_not_draft_format():
    ctx = make_ctx(FakeDraftStore())
    result = _execute_add_note_to_draft(
        {"target_draft_id": "5", "type_name": "评分细则", "content": "x"}, ctx)
    assert "必须是草稿ID" in result


def test_add_note_to_draft_not_found():
    ctx = make_ctx(FakeDraftStore())
    result = _execute_add_note_to_draft(
        {"target_draft_id": "draft-99", "type_name": "评分细则", "content": "x"}, ctx)
    assert "不存在" in result


def test_add_note_to_draft_already_committed():
    ds = FakeDraftStore({"draft-1": _make_draft("draft-1", status="committed")})
    ctx = make_ctx(ds)
    result = _execute_add_note_to_draft(
        {"target_draft_id": "draft-1", "type_name": "评分细则", "content": "x"}, ctx)
    assert "已提交/丢弃" in result


def test_add_note_to_draft_cannot_stack_on_note_draft():
    ds = FakeDraftStore({"draft-1": _make_draft("draft-1", "add_note")})
    ctx = make_ctx(ds)
    result = _execute_add_note_to_draft(
        {"target_draft_id": "draft-1", "type_name": "评分细则", "content": "x"}, ctx)
    assert "不能再叠加备注" in result


def test_add_note_to_draft_type_not_found():
    ds = FakeDraftStore({"draft-1": _make_draft("draft-1")})
    ctx = make_ctx(ds)
    with mock.patch("chains.record_agent_tools.get_note_type_by_name", return_value=None), \
         mock.patch("chains.record_agent_tools.record_log"):
        result = _execute_add_note_to_draft(
            {"target_draft_id": "draft-1", "type_name": "不存在类型", "content": "x"}, ctx)
    assert "不存在" in result


# ========== 消歧校验 ==========

def test_update_question_draft_rejects_draft_id_string():
    ctx = make_ctx(FakeDraftStore())
    with mock.patch("chains.record_agent_tools.get_question_by_id") as m:
        result = _execute_update_question_draft({"target_question_id": "draft-1"}, ctx)
        m.assert_not_called()
    assert "草稿ID" in result and "add_note_to_draft" in result


def test_add_note_draft_rejects_draft_id_string():
    ctx = make_ctx(FakeDraftStore())
    with mock.patch("chains.record_agent_tools.get_question_by_id") as m:
        result = _execute_add_note_draft(
            {"target_question_id": "draft-1", "type_name": "x", "content": "y"}, ctx)
        m.assert_not_called()
    assert "草稿ID" in result and "add_note_to_draft" in result


def test_add_note_draft_warns_when_draft_with_same_number_exists():
    ds = FakeDraftStore({"draft-1": _make_draft("draft-1")})
    ctx = make_ctx(ds)
    with mock.patch("chains.record_agent_tools.get_question_by_id") as m:
        result = _execute_add_note_draft(
            {"target_question_id": 1, "type_name": "x", "content": "y"}, ctx)
        m.assert_not_called()
    assert "草稿 draft-1" in result and "确认意图" in result


# ========== 分发 ==========

def test_dispatch_add_note_to_draft():
    ds = FakeDraftStore({"draft-1": _make_draft("draft-1")})
    ctx = make_ctx(ds)
    with mock.patch("chains.record_agent_tools.get_note_type_by_name",
                    return_value={"id": 3, "type_name": "评分细则"}), \
         mock.patch("chains.record_agent_tools.record_log"):
        result = _execute_record_tool(
            "add_note_to_draft",
            {"target_draft_id": "draft-1", "type_name": "评分细则", "content": "x"},
            ctx)
    assert "已为草稿 draft-1" in result
