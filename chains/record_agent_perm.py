"""录题 Agent 物理权限控件（会话级开关封装 + 工具拦截判定）。

设计要点：
  - 7 个操作类型粒度开关 + 1 个紧急停止总开关
  - 状态存 session_state（会话级，<5ms 读取）
  - 默认全开（向后兼容 v1.2）
  - 紧急停止最高优先级
  - 只读工具 pdf_preview_fragment 跳过所有控件
  - check_tool_permission 纯判定，不修改状态、不写日志（日志由调用方写）
"""
import streamlit as st

OP_TYPES = (
    "create_question",
    "update_question",
    "add_note",
    "insert_table",
    "insert_image",
    "pdf_split",
    "rubric_match",
)

OP_TYPE_LABELS = {
    "create_question": "新建题目",
    "update_question": "修改已有题目",
    "add_note": "添加备注",
    "insert_table": "插入表格片段",
    "insert_image": "插入题目图片",
    "pdf_split": "PDF 多题识别",
    "rubric_match": "评分细则匹配",
}

TOOL_OP_TYPE_MAP = {
    "create_question_draft": "create_question",
    "update_question_draft": "update_question",
    "add_note_draft": "add_note",
    "add_note_to_draft": "add_note",
    "insert_table_fragment": "insert_table",
    "insert_question_image": "insert_image",
    "pdf_upload_and_split": "pdf_split",
    "pdf_match_rubric": "rubric_match",
}

READONLY_TOOLS = frozenset({"pdf_preview_fragment", "find_question"})


class PermissionSwitches:
    """会话级权限开关封装（状态存 streamlit session_state）。"""

    def __init__(self, session_id):
        self._sid = session_id
        self._sw_key = "ra_perm_switches_%s" % session_id
        self._es_key = "ra_perm_emergency_stop_%s" % session_id

    def get_all(self):
        sw = st.session_state.get(self._sw_key)
        if sw is None:
            sw = {op: True for op in OP_TYPES}
            st.session_state[self._sw_key] = sw
        return sw

    def get_emergency_stop(self):
        if self._es_key not in st.session_state:
            st.session_state[self._es_key] = False
        return st.session_state[self._es_key]

    def set_switch(self, op_type, allowed):
        if op_type not in OP_TYPES:
            return
        sw = self.get_all()
        sw[op_type] = bool(allowed)

    def set_emergency_stop(self, stopped):
        st.session_state[self._es_key] = bool(stopped)

    def is_default(self):
        if self.get_emergency_stop():
            return False
        return all(self.get_all().values())


def check_tool_permission(tool_name, switches):
    """工具权限拦截判定（纯判定，不修改状态、不写日志）。

    返回 (allowed, reason, switch_name)：
      - reason 取值 emergency_stop / switch_off / default_deny / ""
      - switch_name 为中文标签（拒绝时供 UI 提示）
    """
    try:
        if tool_name in READONLY_TOOLS:
            return (True, "", "")
        if switches.get_emergency_stop():
            return (False, "emergency_stop", "紧急停止")
        op_type = TOOL_OP_TYPE_MAP.get(tool_name)
        if op_type is None:
            return (False, "default_deny", "")
        sw = switches.get_all()
        if not sw.get(op_type, False):
            return (False, "switch_off", OP_TYPE_LABELS.get(op_type, op_type))
        return (True, "", "")
    except Exception:
        return (False, "default_deny", "")
