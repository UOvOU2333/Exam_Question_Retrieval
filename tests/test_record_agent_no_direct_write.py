"""禁直写机制单元测试。

安全核心约束：record_agent_tools.py 禁止 import / 调用写库服务层函数。
通过 inspect 检查模块源码确保无写库 import。
"""
import inspect
import importlib


def test_no_write_import_in_record_agent_tools():
    """record_agent_tools 模块源码不含写库函数 import。"""
    mod = importlib.import_module("chains.record_agent_tools")
    source = inspect.getsource(mod)
    forbidden = ["create_question", "update_question", "create_question_note"]
    # 允许出现在注释/字符串中的情况需人工审查，此处检查 import 行
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("from ") or stripped.startswith("import "):
            for fn in forbidden:
                assert fn not in stripped, "禁直写违规: %s 出现在 import 行: %s" % (fn, line)


def test_tool_whitelist_complete():
    """工具白名单含 10 个工具（含只读 find_question），不含写库工具。"""
    from chains.record_agent_tools import RECORD_AGENT_TOOL_NAMES
    expected = {
        "find_question",
        "create_question_draft", "update_question_draft", "add_note_draft",
        "add_note_to_draft",
        "insert_table_fragment", "insert_question_image",
        "pdf_upload_and_split", "pdf_match_rubric", "pdf_preview_fragment",
    }
    assert RECORD_AGENT_TOOL_NAMES == expected, "工具白名单不匹配: %s" % RECORD_AGENT_TOOL_NAMES


def test_no_write_tool_in_whitelist():
    """工具白名单不含直接写库的工具名。"""
    from chains.record_agent_tools import RECORD_AGENT_TOOL_NAMES
    forbidden_tools = {"create_question", "update_question", "create_question_note", "delete_question"}
    assert not (RECORD_AGENT_TOOL_NAMES & forbidden_tools), "白名单含写库工具"
