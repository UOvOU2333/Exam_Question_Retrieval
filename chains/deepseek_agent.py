import json
import os
import requests
from datetime import datetime

from services.question_services import search_questions, get_question_by_id
from services.note_services import get_question_notes, search_notes
from tools.exam_type_utils import QUESTION_TYPES, KNOWLEDGE_MODULES
from utils.permissions import can_view_analysis

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"
MAX_ITERATIONS = 8
SEARCH_RESULT_LIMIT = 12
CONTENT_PREVIEW_LEN = 100

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_questions",
            "description": "在高中政治题库中按条件检索题目。根据用户问题提取关键词和筛选条件进行搜索，返回匹配题目的ID、简要内容和元信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "在题目内容/答案/解析中搜索的关键词，提取用户问题中的核心概念，如 全过程人民民主、供给侧结构性改革"},
                    "paper_type": {"type": "string", "description": "卷种名称，如 浙江首考、全国甲卷、北京卷、新课标卷、山东卷"},
                    "question_no": {"type": "string", "description": "题号，如 5、T3"},
                    "years": {"type": "array", "items": {"type": "integer"}, "description": "年份列表，如 [2024, 2023]"},
                    "question_type": {"type": "string", "enum": QUESTION_TYPES, "description": "题型筛选"},
                    "knowledge_modules": {"type": "array", "items": {"type": "string", "enum": KNOWLEDGE_MODULES}, "description": "知识模块列表（可多选）"},
                    "search_scope": {"type": "string", "enum": ["qa", "source"], "description": "搜索范围：qa=题目/答案/解析(默认)，source=来源/解析来源"},
                    "new_textbook_only": {"type": "boolean", "description": "是否仅搜索新教材题目，默认false"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_question",
            "description": "根据题目ID获取完整详情，包括题目内容、答案、解析、来源、年份、卷种、题号、题型、知识模块。当需要查看或讲解某道题的完整内容时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question_id": {"type": "integer", "description": "题目ID"},
                },
                "required": ["question_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_question_notes",
            "description": "获取指定题目下的所有备注（如知识模块、评分细则、个人解析、其他版本解析等），按用户权限过滤可见范围。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question_id": {"type": "integer", "description": "题目ID"},
                },
                "required": ["question_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": "按关键词搜索备注内容，返回匹配备注及其关联题目。适用于通过备注内容查找相关题目。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "在备注内容中搜索的关键词"},
                    "note_type_name": {"type": "string", "description": "可选，限定备注类型名称，如 知识模块、评分细则、评价与个人解析、其他版本解析、试题类型、相关概念或知识"},
                },
                "required": ["keyword"],
            },
        },
    },
]


def _build_system_prompt() -> str:
    today = datetime.now().strftime("%Y年%m月%d日")
    return (
        "你是高中政治学科题库智能助手。通过调用检索工具在题库中查找题目，并基于检索结果回答用户问题。\n\n"
        "本系统仅包含高中政治题目，不涉及历史、地理、物理、化学、生物等其他学科。\n\n"
        "工作流程：\n"
        "1. 分析用户问题，提取检索关键词和结构化筛选条件（卷种、年份、题型、知识模块等）。\n"
        "2. 调用 search_questions 检索。若结果不理想，可换用不同关键词或放宽/收紧条件再次检索（最多尝试3次）。\n"
        "3. 对需要详细解答的题目，调用 get_question 获取完整内容、答案与解析。\n"
        "4. 若用户想了解题目备注（知识模块、评分细则、个人解析、其他版本解析等），调用 get_question_notes；若想通过备注内容找题，调用 search_notes。\n"
        "5. 综合检索结果组织回答，引用题目时标注【题目ID】。\n\n"
        f"参数取值参考：\n"
        f"- question_type 可选：{QUESTION_TYPES}\n"
        f"- knowledge_modules 可选：{KNOWLEDGE_MODULES}\n"
        "- 常见卷种：浙江首考、浙江高考、全国甲卷、新课标卷、北京卷、天津卷、山东卷、江苏卷、广东卷等。\n\n"
        f"今天是 {today}。判断“最近”“今年”等时间词时据此换算正确年份。\n\n"
        "回答要求：\n"
        "- 用简体中文回答。\n"
        "- 检索到多道题目时，用 markdown 表格展示（列：题目ID | 年份 | 卷种 | 题号 | 题型 | 内容摘要）；单道题可直接展示完整内容。\n"
        "- 用户想看某道题的详细解答时，调用 get_question 后给出完整答案和解析。\n"
        "- 未检索到时如实告知，并建议调整关键词或条件。\n"
        "- 严禁编造题目内容，所有信息必须来自工具检索结果。\n"
        "- 若工具返回解析不可见提示，应如实告知用户当前角色无权查看解析，不要编造解析内容。"
    )


def _execute_search_questions(args: dict, role: str | None = None) -> str:
    include_analysis = can_view_analysis(role) if role else True
    qids = search_questions(
        paper_type=args.get("paper_type"),
        question_no=args.get("question_no"),
        keyword=args.get("keyword"),
        years=args.get("years") or None,
        search_scope=args.get("search_scope", "qa"),
        new_textbook_only=bool(args.get("new_textbook_only", False)),
        question_type=args.get("question_type"),
        knowledge_modules=args.get("knowledge_modules") or None,
        include_analysis=include_analysis,
    )
    if not qids:
        return "未找到符合条件的题目。"

    show = qids[:SEARCH_RESULT_LIMIT]
    lines = [f"共找到 {len(qids)} 道题目，列出前 {len(show)} 道：", ""]
    lines.append("| ID | 年份 | 卷种 | 题号 | 题型 | 内容摘要 |")
    lines.append("|---:|:---:|:---:|:---:|:---:|:---|")
    for qid in show:
        q = get_question_by_id(qid)
        if not q:
            continue
        content = (q["content"] or "")[:30].replace("\n", " ").replace("|", "／").strip()
        lines.append(
            f"| {q['questionID']} | {q['year'] or ''} | {q['paper_type'] or ''} | "
            f"{q['question_no'] or ''} | {q['question_type'] or ''} | {content} |"
        )
    if len(qids) > SEARCH_RESULT_LIMIT:
        lines.append(f"\n还有 {len(qids) - SEARCH_RESULT_LIMIT} 道未列出，可缩小条件范围后检索。")
    return "\n".join(lines)


def _execute_get_question(args: dict, role: str | None = None) -> str:
    qid = args.get("question_id")
    q = get_question_by_id(qid)
    if not q:
        return f"未找到ID为 {qid} 的题目。"
    if q["isInRecycleBin"] == 1:
        return f"题目ID {qid} 已在回收站中。"
    show_analysis = can_view_analysis(role) if role else True
    lines = [
        f"【题目ID】{q['questionID']}",
        f"【题目】{q['content']}",
        f"【答案】{q['answer']}",
    ]
    if show_analysis:
        lines.append(f"【解析】{q['analysis']}")
        lines.append(f"【解析来源】{q['analysis_source']}")
    else:
        lines.append("【解析】当前角色无权查看解析内容")
    lines.append(f"【来源】{q['source']}")
    lines.append(f"【年份】{q['year'] or '未知'}")
    lines.append(f"【卷种】{q['paper_type'] or '未知'}")
    lines.append(f"【题号】{q['question_no'] or '未知'}")
    lines.append(f"【题型】{q['question_type'] or '未知'}")
    lines.append(f"【知识模块】{q['knowledge_modules'] or '未知'}")
    return "\n".join(lines)


def _execute_get_question_notes(args: dict, role: str | None) -> str:
    qid = args.get("question_id")
    notes = get_question_notes(qid, viewer_role=role)
    if not notes:
        return f"题目ID {qid} 下没有可见备注。"
    lines = [f"题目ID {qid} 共 {len(notes)} 条备注："]
    for n in notes:
        content = (n["content"] or "")[:200].replace("\n", " ")
        lines.append(f"[备注ID {n['note_id']}] 类型:{n['type_name']} | {content}")
    return "\n".join(lines)


def _execute_search_notes(args: dict, role: str | None) -> str:
    keyword = args.get("keyword")
    notes = search_notes(keyword, note_type_name=args.get("note_type_name"), viewer_role=role)
    if not notes:
        return f"未找到内容含「{keyword}」的备注。"
    lines = [f"共找到 {len(notes)} 条匹配备注：", ""]
    lines.append("| 备注ID | 题目ID | 年份 | 卷种 | 题号 | 类型 | 内容摘要 |")
    lines.append("|---:|---:|:---:|:---:|:---:|:---|:---|")
    for n in notes[:15]:
        content = (n["content"] or "")[:30].replace("\n", " ").replace("|", "／").strip()
        lines.append(
            f"| {n['note_id']} | {n['question_id']} | {n['year'] or ''} | "
            f"{n['paper_type'] or ''} | {n['question_no'] or ''} | {n['type_name']} | {content} |"
        )
    if len(notes) > 15:
        lines.append(f"\n还有 {len(notes) - 15} 条未列出。")
    return "\n".join(lines)


def _execute_tool(name: str, args: dict, role: str | None = None) -> str:
    try:
        if name == "search_questions":
            return _execute_search_questions(args, role)
        if name == "get_question":
            return _execute_get_question(args, role)
        if name == "get_question_notes":
            return _execute_get_question_notes(args, role)
        if name == "search_notes":
            return _execute_search_notes(args, role)
        return f"未知工具: {name}"
    except Exception as e:
        return f"工具执行出错({name}): {e}"


def get_api_key() -> str | None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("deepseek_api_key")
    except Exception:
        return None


def run_agent(
    history: list,
    user_input: str,
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    user_role: str | None = None,
):
    """
    运行 DeepSeek function-calling agent。
    history: [{"role": "user"|"assistant", "content": str}, ...]（不含 system）
    返回: (answer: str, steps: list[dict])
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{base_url.rstrip('/')}/chat/completions"
    steps = []

    working = [{"role": "system", "content": _build_system_prompt()}]
    for m in history:
        working.append({"role": m["role"], "content": m["content"]})
    working.append({"role": "user", "content": user_input})

    for _ in range(MAX_ITERATIONS):
        payload = {"model": model, "messages": working, "tools": TOOLS, "stream": False}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
        except requests.RequestException as e:
            steps.append({"error": f"网络请求失败: {e}"})
            return "网络请求失败，请检查网络连接和 API 地址。", steps

        if resp.status_code != 200:
            steps.append({"error": f"HTTP {resp.status_code}: {resp.text[:300]}"})
            return f"调用 AI 服务失败（HTTP {resp.status_code}），请检查 API Key、模型名与网络。", steps

        try:
            data = resp.json()
            msg = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError) as e:
            steps.append({"error": f"解析响应失败: {e}"})
            return "AI 服务返回数据异常。", steps

        working.append({
            "role": "assistant",
            "content": msg.get("content"),
            "tool_calls": msg.get("tool_calls"),
        })

        tool_calls = msg.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                fn = tc["function"]
                tname = fn["name"]
                try:
                    targs = json.loads(fn["arguments"] or "{}")
                except json.JSONDecodeError:
                    targs = {}
                result = _execute_tool(tname, targs, role=user_role)
                steps.append({"tool": tname, "args": targs, "result": result[:1500]})
                working.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })
            continue

        return msg.get("content") or "", steps

    return "已达最大推理轮次，未能生成最终回答，请尝试换一种问法。", steps
