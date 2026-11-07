"""录题 Agent 物理权限控件单测。"""
from unittest import mock

import pytest

from chains.record_agent_perm import (
    OP_TYPES,
    OP_TYPE_LABELS,
    TOOL_OP_TYPE_MAP,
    READONLY_TOOLS,
    PermissionSwitches,
    check_tool_permission,
)


@pytest.fixture
def fake_ss():
    d = {}
    with mock.patch("chains.record_agent_perm.st") as m:
        m.session_state = d
        yield d


def test_default_all_open(fake_ss):
    sw = PermissionSwitches("s1")
    assert set(sw.get_all().keys()) == set(OP_TYPES)
    assert all(sw.get_all().values())
    assert sw.get_emergency_stop() is False
    assert sw.is_default() is True


def test_default_all_tools_allowed(fake_ss):
    sw = PermissionSwitches("s1")
    for tname in list(TOOL_OP_TYPE_MAP.keys()) + list(READONLY_TOOLS):
        allowed, reason, _ = check_tool_permission(tname, sw)
        assert allowed is True
        assert reason == ""


def test_emergency_stop_blocks_writes_not_readonly(fake_ss):
    sw = PermissionSwitches("s1")
    sw.set_emergency_stop(True)
    assert sw.get_emergency_stop() is True
    assert sw.is_default() is False
    for tname in TOOL_OP_TYPE_MAP.keys():
        allowed, reason, sname = check_tool_permission(tname, sw)
        assert allowed is False
        assert reason == "emergency_stop"
        assert sname == "紧急停止"
    allowed, reason, _ = check_tool_permission("pdf_preview_fragment", sw)
    assert allowed is True
    assert reason == ""


def test_single_switch_off_blocks_only_mapped_tool(fake_ss):
    sw = PermissionSwitches("s1")
    sw.set_switch("update_question", False)
    allowed, reason, sname = check_tool_permission("update_question_draft", sw)
    assert allowed is False
    assert reason == "switch_off"
    assert sname == OP_TYPE_LABELS["update_question"]
    for tname in ["create_question_draft", "add_note_draft", "insert_table_fragment",
                  "insert_question_image", "pdf_upload_and_split", "pdf_match_rubric",
                  "pdf_preview_fragment"]:
        allowed, _, _ = check_tool_permission(tname, sw)
        assert allowed is True


def test_unknown_tool_default_deny(fake_ss):
    sw = PermissionSwitches("s1")
    allowed, reason, _ = check_tool_permission("some_unknown_tool", sw)
    assert allowed is False
    assert reason == "default_deny"


def test_exception_returns_default_deny(fake_ss):
    class BadSw:
        def get_emergency_stop(self):
            raise RuntimeError("boom")
        def get_all(self):
            raise RuntimeError("boom")
    allowed, reason, _ = check_tool_permission("create_question_draft", BadSw())
    assert allowed is False
    assert reason == "default_deny"


def test_set_switch_unknown_op_no_effect(fake_ss):
    sw = PermissionSwitches("s1")
    sw.set_switch("nonexistent_op", True)
    assert "nonexistent_op" not in sw.get_all()


def test_persistence_across_instances_same_sid(fake_ss):
    sw1 = PermissionSwitches("s1")
    sw1.set_switch("add_note", False)
    sw1.set_emergency_stop(True)
    sw2 = PermissionSwitches("s1")
    assert sw2.get_all()["add_note"] is False
    assert sw2.get_emergency_stop() is True


def test_different_sid_isolated(fake_ss):
    sw1 = PermissionSwitches("s1")
    sw1.set_emergency_stop(True)
    sw2 = PermissionSwitches("s2")
    assert sw2.get_emergency_stop() is False
    assert sw2.is_default() is True
