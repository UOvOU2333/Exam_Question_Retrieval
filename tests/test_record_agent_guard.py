"""录题 Agent 物理控件拦截层单测。

mock DeepSeek API 返回 tool_call，验证拦截判定在白名单后、tool_call_count+=1 前生效。
"""
import json
from unittest import mock

import pytest

from chains.record_agent_perm import PermissionSwitches


def _api_resp_tool(tool_name, args=None, call_id="c1"):
    return mock.Mock(
        status_code=200,
        json=mock.Mock(return_value={
            "choices": [{
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": call_id, "type": "function",
                        "function": {"name": tool_name, "arguments": json.dumps(args or {})},
                    }],
                }
            }]
        }),
        text="",
    )


def _api_resp_text(text="完成"):
    return mock.Mock(
        status_code=200,
        json=mock.Mock(return_value={
            "choices": [{"message": {"role": "assistant", "content": text}}]
        }),
        text="",
    )


class FakeDraftStore:
    def list_all(self):
        return []

    def get(self, draft_id):
        return None


@pytest.fixture
def fake_ss():
    d = {}
    with mock.patch("chains.record_agent_perm.st") as m:
        m.session_state = d
        yield d


def _run(tool_name, tool_args, perm_switches, fake_ss, extra_responses=None):
    from chains.record_agent import run_record_agent
    responses = [_api_resp_tool(tool_name, tool_args)] + (extra_responses or [_api_resp_text()])
    with mock.patch("chains.record_agent.requests.post", side_effect=responses), \
         mock.patch("chains.record_agent.is_record_agent_enabled", return_value=True), \
         mock.patch("chains.record_agent.is_admin", return_value=True), \
         mock.patch("chains.record_agent.record_log"), \
         mock.patch("chains.record_agent._execute_record_tool", return_value="工具执行结果"):
        return run_record_agent(
            history=[], user_input="测试", api_key="fake",
            user_role="admin", user_id=1, session_id="s1",
            draft_store=FakeDraftStore(), perm_switches=perm_switches,
        )


def _tool_steps(steps):
    return [s for s in steps if s.get("tool")]


def test_none_switches_no_interception(fake_ss):
    answer, steps, _ = _run("create_question_draft", {"content": "x"}, None, fake_ss)
    ts = _tool_steps(steps)
    assert any("工具执行结果" in s.get("result", "") for s in ts)


def test_emergency_stop_blocks_write(fake_ss):
    sw = PermissionSwitches("s1")
    sw.set_emergency_stop(True)
    answer, steps, _ = _run("create_question_draft", {"content": "x"}, sw, fake_ss)
    ts = _tool_steps(steps)
    assert any("已被禁用" in s.get("result", "") for s in ts)


def test_emergency_stop_allows_readonly(fake_ss):
    sw = PermissionSwitches("s1")
    sw.set_emergency_stop(True)
    answer, steps, _ = _run("pdf_preview_fragment", {"file_id": "x"}, sw, fake_ss)
    ts = _tool_steps(steps)
    assert any("工具执行结果" in s.get("result", "") for s in ts)


def test_single_switch_off_blocks_mapped_tool(fake_ss):
    sw = PermissionSwitches("s1")
    sw.set_switch("update_question", False)
    answer, steps, _ = _run("update_question_draft", {"target_question_id": 1}, sw, fake_ss)
    ts = _tool_steps(steps)
    assert any("已被禁用" in s.get("result", "") for s in ts)
    assert any("修改已有题目" in s.get("result", "") for s in ts)


def test_single_switch_off_other_tools_pass(fake_ss):
    sw = PermissionSwitches("s1")
    sw.set_switch("update_question", False)
    answer, steps, _ = _run("create_question_draft", {"content": "x"}, sw, fake_ss)
    ts = _tool_steps(steps)
    assert any("工具执行结果" in s.get("result", "") for s in ts)


def test_interception_does_not_consume_budget(fake_ss):
    """拦截不消耗 tool_call_count：被拦截后只读工具仍放行。"""
    from chains.record_agent import run_record_agent
    sw = PermissionSwitches("s1")
    sw.set_switch("create_question", False)
    responses = [
        _api_resp_tool("create_question_draft", {"content": "x"}, call_id="c1"),
        _api_resp_tool("pdf_preview_fragment", {"file_id": "x"}, call_id="c2"),
        _api_resp_text(),
    ]
    with mock.patch("chains.record_agent.requests.post", side_effect=responses), \
         mock.patch("chains.record_agent.is_record_agent_enabled", return_value=True), \
         mock.patch("chains.record_agent.is_admin", return_value=True), \
         mock.patch("chains.record_agent.record_log"), \
         mock.patch("chains.record_agent._execute_record_tool", return_value="工具执行结果"):
        answer, steps, _ = run_record_agent(
            history=[], user_input="测试", api_key="fake",
            user_role="admin", user_id=1, session_id="s1",
            draft_store=FakeDraftStore(), perm_switches=sw,
        )
    ts = _tool_steps(steps)
    assert any("已被禁用" in s.get("result", "") for s in ts)
    assert any("工具执行结果" in s.get("result", "") for s in ts)


def test_interception_writes_permission_denied_log(fake_ss):
    """拦截写 permission_denied 日志（detail.layer=tool_guard）。"""
    from chains.record_agent import run_record_agent
    sw = PermissionSwitches("s1")
    sw.set_emergency_stop(True)
    log_calls = []
    def _capture_log(**kwargs):
        log_calls.append(kwargs)
    responses = [_api_resp_tool("create_question_draft", {"content": "x"}), _api_resp_text()]
    with mock.patch("chains.record_agent.requests.post", side_effect=responses), \
         mock.patch("chains.record_agent.is_record_agent_enabled", return_value=True), \
         mock.patch("chains.record_agent.is_admin", return_value=True), \
         mock.patch("chains.record_agent.record_log", side_effect=_capture_log), \
         mock.patch("chains.record_agent._execute_record_tool", return_value="x"):
        run_record_agent(
            history=[], user_input="测试", api_key="fake",
            user_role="admin", user_id=1, session_id="s1",
            draft_store=FakeDraftStore(), perm_switches=sw,
        )
    guard_logs = [c for c in log_calls
                  if c.get("action") == "permission_denied"
                  and c.get("detail", {}).get("layer") == "tool_guard"]
    assert len(guard_logs) >= 1
    assert guard_logs[0]["detail"]["reason"] == "emergency_stop"
