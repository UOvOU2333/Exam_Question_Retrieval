# question_tools.py
from typing import List, Optional, Dict, Any
from langchain.tools import tool
from services.question_services import (
    search_questions,
    get_question_by_id,
    create_question,
    update_question,
    move_to_recycle_bin,
    search_by_note,
)
from services.user_services import get_user_by_id
from chains.loger import trace
import sqlite3
import urllib.parse

# ---------- 权限辅助函数 ----------
def _check_read_permission(role: str) -> bool:
    return role in ("viewer", "editor", "admin")

def _check_write_permission(role: str) -> bool:
    return role in ("editor", "admin")

def _check_admin_permission(role: str) -> bool:
    return role == "admin"

# ---------- 工具1：搜索题目 ----------
@tool
def search_questions_tool(
    paper_type: Optional[str] = None,
    question_no: Optional[str] = None,
    keyword: Optional[str] = None,
    years: Optional[List[int]] = None,
    search_scope: str = "qa",
    new_textbook_only: bool = False,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    根据卷种、题号、关键词、年份等条件搜索题目。
    new_textbook_only: 仅搜索新教材题目（True=仅新教材，False=不限）。
    返回匹配题目的 ID 列表及简要信息（需进一步调用 get_question_tool 获取详情）。
    权限：viewer / editor / admin
    """

    # ========== 智能参数规范化（处理 LLM 常见错误） ==========
    def _normalize(paper_type, question_no, keyword, years, search_scope, new_textbook_only):
        # 情况1：paper_type 是字典
        if isinstance(paper_type, dict):
            trace("QuestionTools", f"{role} {user_id} AutoUnpackDict", str(paper_type))
            return (
                paper_type.get("paper_type"),
                paper_type.get("question_no") or question_no,
                paper_type.get("keyword") or keyword,
                paper_type.get("years") or years,
                paper_type.get("search_scope") or search_scope,
                paper_type.get("new_textbook_only", new_textbook_only),
            )
        # 情况2：paper_type 是字符串且包含 '=' 和 '&'（查询字符串）
        if isinstance(paper_type, str) and '=' in paper_type and ('&' in paper_type or '&' in paper_type):
            trace("QuestionTools", f"{role} {user_id} AutoUnpackQueryString", paper_type)
            params = {}
            for part in paper_type.split('&'):
                if '=' not in part:
                    continue
                k, v = part.split('=', 1)
                k = k.strip()
                v = v.strip()
                # 尝试解析列表格式 [2024,2023]
                if v.startswith('[') and v.endswith(']'):
                    inner = v[1:-1].strip()
                    if inner:
                        params[k] = [int(x.strip()) for x in inner.split(',') if x.strip().isdigit()]
                    else:
                        params[k] = []
                else:
                    params[k] = v
            return (
                params.get("paper_type"),
                params.get("question_no") or question_no,
                params.get("keyword") or keyword,
                params.get("years") or years,
                params.get("search_scope") or search_scope,
                params.get("new_textbook_only", new_textbook_only),
            )
        # 情况3：正常
        return (paper_type, question_no, keyword, years, search_scope, new_textbook_only)

    paper_type, question_no, keyword, years, search_scope, new_textbook_only = _normalize(
        paper_type, question_no, keyword, years, search_scope, new_textbook_only
    )
    # 确保 new_textbook_only 是布尔类型
    if isinstance(new_textbook_only, str):
        new_textbook_only = new_textbook_only.lower() in ("true", "1", "yes")
    # =======================================================

    trace("QuestionTools", f"{role} {user_id} Search",
          f"paper_type={paper_type}, question_no={question_no}, keyword={keyword}, years={years}, search_scope={search_scope}, new_textbook_only={new_textbook_only}")

    if not _check_read_permission(role):
        return "错误：您没有查看题目的权限（需要 viewer / editor / admin 角色）"

    try:
        qids = search_questions(
            paper_type=paper_type,
            question_no=question_no,
            keyword=keyword,
            years=years,
            field_que="all",
            field_sou="all",
            search_scope=search_scope,
            no_fuzzy=False,
            new_textbook_only=bool(new_textbook_only),
        )
        if not qids:
            trace("QuestionTools", f"{role} {user_id} Search Result", "no results")
            return "未找到符合条件的题目。"
        
        count = len(qids)
        trace("QuestionTools", f"{role} {user_id} Search Result", f"found {count} questions")
        results = []
        for qid in qids[:10]:
            q = get_question_by_id(qid)
            if q:
                # 兼容 sqlite3.Row 和 dict
                content = q.get("content") if hasattr(q, "get") else q["content"]
                results.append(f"ID {q['questionID']}: {content[:50]}...")
        summary = "\n".join(results)
        if len(qids) > 10:
            summary += f"\n... 共 {len(qids)} 条结果，仅显示前10条。"
        return f"找到 {len(qids)} 道题目：\n{summary}"
    except Exception as e:
        trace("QuestionTools", f"{role} {user_id} Search Error", str(e), level="error")
        return f"搜索题目时发生错误：{str(e)}"

# ---------- 工具2：获取单题详情 ----------
@tool
def get_question_tool(question_id: int, user_id: int = None, role: str = None) -> str:
    """
    根据题目ID获取完整信息（题目、答案、解析、来源、年份、卷种、题号）。
    权限：viewer / editor / admin
    """

    trace("QuestionTools", f"{role} {user_id} Get", f"question_id={question_id}")

    if not _check_read_permission(role):
        return "错误：您没有查看题目的权限（需要 viewer / editor / admin 角色）"

    try:
        q = get_question_by_id(question_id)
        if isinstance(q, sqlite3.Row):
            q = dict(q)
        if not q or q.get("isInRecycleBin") == 1:
            trace("QuestionTools", f"{role} {user_id} Get Result", f"question_id={question_id} not found or in recycle bin")
            return f"未找到ID为 {question_id} 的题目，或该题目已在回收站中。"
        
        trace("QuestionTools", f"{role} {user_id} Get Result", f"success: question_id={question_id} retrieved")
        lines = [
            f"【题目ID】{q['questionID']}",
            f"【题目】{q['content']}",
            f"【答案】{q['answer']}",
            f"【解析】{q['analysis']}",
            f"【来源】{q['source']}",
            f"【解析来源】{q['analysis_source']}",
            f"【年份】{q['year'] or '未知'}",
            f"【卷种】{q['paper_type'] or '未知'}",
            f"【题号】{q['question_no'] or '未知'}",
        ]
        return "\n".join(lines)
    except Exception as e:
        trace("QuestionTools", f"{role} {user_id} Get Error", str(e), level="error")
        return f"获取题目详情时发生错误：{str(e)}"

# ---------- 工具3：创建题目 ----------
@tool
def create_question_tool(
    content: str,
    answer: Optional[str] = None,
    analysis: Optional[str] = None,
    source: Optional[str] = None,
    analysis_source: Optional[str] = None,
    year: Optional[int] = None,
    paper_type: Optional[str] = None,
    question_no: Optional[str] = None,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    创建一道新题目。
    权限：editor / admin
    """
    # ========== 防御性参数解析 ==========
    # 情况1：模型将所有参数打包成一个字典传入（第一个参数 content 实际是字典）
    if isinstance(content, dict):
        params = content
        # 递归提取真正的 content 字符串（可能有多层嵌套）
        def _extract_string_from_dict(d, key="content"):
            """从嵌套字典中提取指定 key 的字符串值"""
            val = d.get(key)
            while isinstance(val, dict):
                val = val.get(key)
            return val if isinstance(val, str) else None

        content = _extract_string_from_dict(params, "content")
        answer = params.get("answer", answer)
        analysis = params.get("analysis", analysis)
        source = params.get("source", source)
        analysis_source = params.get("analysis_source", analysis_source)
        year = params.get("year", year)
        paper_type = params.get("paper_type", paper_type)
        question_no = params.get("question_no", question_no)

    # 情况2：content 不是字符串，尝试转换
    if not isinstance(content, str):
        if content is None:
            content = ""
        else:
            content = str(content)

    # 校验 content 不能为空
    if not content or not content.strip():
        return "错误：题目内容不能为空。"

    trace("QuestionTools", f"{role} {user_id} Create", f"year={year}, paper_type={paper_type}, question_no={question_no}")

    if not _check_write_permission(role):
        return "错误：您没有创建题目的权限（需要 editor 或 admin 角色）"

    # 答案和解析不可为空，若未提供则填入“无”
    final_answer = answer if answer is not None else "无"
    if final_answer == "":
        final_answer = "无"
    final_analysis = analysis if analysis is not None else "无"
    if final_analysis == "":
        final_analysis = "无"

    try:
        qid = create_question(
            content=content,
            answer=final_answer,
            analysis=final_analysis,
            source=source if source is not None else "",
            analysis_source=analysis_source if analysis_source is not None else "",
            year=year,
            paper_type=paper_type,
            question_no=question_no,
        )
        trace("QuestionTools", f"{role} {user_id} Create Result", f"success: question_id={qid}")
        return f"题目创建成功！新题目ID为 {qid}。"
    except Exception as e:
        trace("QuestionTools", f"{role} {user_id} Create Error", str(e), level="error")
        return f"创建题目时发生错误：{str(e)}"


# ---------- 工具4：更新题目 ----------
@tool
def update_question_tool(
    question_id: int,
    content: Optional[str] = None,
    answer: Optional[str] = None,
    analysis: Optional[str] = None,
    source: Optional[str] = None,
    analysis_source: Optional[str] = None,
    year: Optional[int] = None,
    paper_type: Optional[str] = None,
    question_no: Optional[str] = None,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    更新已存在的题目信息（只更新提供的字段）。
    权限：editor / admin
    """
    # ========== 防御性参数解析 ==========
    # 情况1：模型将所有参数打包成一个字典传入
    if isinstance(question_id, dict):
        params = question_id
        question_id = params.get("question_id")
        # 对于 content，也要递归提取字符串
        raw_content = params.get("content")
        if isinstance(raw_content, dict):
            # 递归提取真正的 content 字符串
            while isinstance(raw_content, dict):
                raw_content = raw_content.get("content")
            content = raw_content if isinstance(raw_content, str) else content
        else:
            content = raw_content if raw_content is not None else content

        answer = params.get("answer", answer)
        analysis = params.get("analysis", analysis)
        source = params.get("source", source)
        analysis_source = params.get("analysis_source", analysis_source)
        year = params.get("year", year)
        paper_type = params.get("paper_type", paper_type)
        question_no = params.get("question_no", question_no)

    # 情况2：模型将字符串（如 "1169" 或 "question_id=1169"）传入
    elif isinstance(question_id, str):
        import re
        match = re.search(r'\d+', question_id)
        if match:
            question_id = int(match.group())
        else:
            return f"错误：无法从 '{question_id}' 中解析出题目ID。请直接提供数字，例如 1169。"

    # 确保 question_id 是正整数
    if not isinstance(question_id, int) or question_id <= 0:
        return f"错误：无效的题目ID '{question_id}'。"

    # 如果 content 传入的是字典（理论上不会，但防御），递归提取字符串
    if isinstance(content, dict):
        while isinstance(content, dict):
            content = content.get("content")
        if not isinstance(content, str):
            content = None

    # ========== 原有权限和查询逻辑 ==========
    trace("QuestionTools", f"{role} {user_id} Update", f"question_id={question_id}")

    if not _check_write_permission(role):
        return "错误：您没有更新题目的权限（需要 editor 或 admin 角色）"

    old = get_question_by_id(question_id)
    if isinstance(old, sqlite3.Row):
        old = dict(old)
    if not old or old.get("isInRecycleBin") == 1:
        return f"未找到ID为 {question_id} 的题目，或该题目已在回收站中。"

    # 处理新值：若字段被提供且为空字符串，则转为“无”（仅对 answer/analysis）
    def normalize_nonempty(val, old_val):
        if val is None:
            return old_val
        if val == "":
            return "无"
        return val

    new_content = content if content is not None else old["content"]
    new_answer = normalize_nonempty(answer, old["answer"])
    new_analysis = normalize_nonempty(analysis, old["analysis"])
    new_source = source if source is not None else old["source"]
    new_analysis_source = analysis_source if analysis_source is not None else old["analysis_source"]
    new_year = year if year is not None else old["year"]
    new_paper_type = paper_type if paper_type is not None else old["paper_type"]
    new_question_no = question_no if question_no is not None else old["question_no"]

    try:
        update_question(
            qid=question_id,
            content=new_content,
            answer=new_answer,
            analysis=new_analysis,
            source=new_source,
            analysis_source=new_analysis_source,
            year=new_year,
            paper_type=new_paper_type,
            question_no=new_question_no,
        )
        return f"题目ID {question_id} 更新成功。"
    except Exception as e:
        return f"更新题目时发生错误：{str(e)}"

# ---------- 工具5：软删除题目（移入回收站） ----------
@tool
def delete_question_tool(question_id: int, user_id: int = None, role: str = None) -> str:
    """
    将题目移入回收站（软删除）。回收站中的题目不会在普通搜索中出现。
    权限：editor / admin
    """

    trace("QuestionTools", f"{role} {user_id} Delete", f"question_id={question_id}")

    if not _check_write_permission(role):
        return "错误：您没有删除题目的权限（需要 editor 或 admin 角色）"

    try:
        move_to_recycle_bin(question_id)
        trace("QuestionTools", f"{role} {user_id} Delete Result", f"success: question_id={question_id} moved to recycle bin")
        return f"题目ID {question_id} 已移入回收站。"
    except Exception as e:
        trace("QuestionTools", f"{role} {user_id} Delete Error", str(e), level="error")
        return f"删除题目时发生错误：{str(e)}"

# ---------- 工具6：根据笔记内容搜索题目 ----------
@tool
def search_question_by_note_tool(
    type_id: Optional[int] = None,
    content_keyword: Optional[str] = None,
    created_by: Optional[str] = None,
    fuzzy: bool = True,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    根据笔记的标签ID、笔记内容关键词、笔记创建人（用户名）搜索关联的题目。
    权限：viewer / editor / admin
    """

    trace("QuestionTools", f"{role} {user_id} SearchByNote", f"type_id={type_id}, content_keyword={content_keyword}, created_by={created_by}")

    if not _check_read_permission(role):
        return "错误：您没有查看笔记的权限（需要 viewer / editor / admin 角色）"

    try:
        qids = search_by_note(
            type_id=type_id,
            content=content_keyword,
            created_by=created_by,
            fuzzy=fuzzy,
        )
        if not qids:
            trace("QuestionTools", f"{role} {user_id} SearchByNote Result", "no results")
            return "未找到符合条件的题目（基于笔记条件）。"
        
        count = len(qids)
        trace("QuestionTools", f"{role} {user_id} SearchByNote Result", f"found {count} questions")
        results = []
        for qid in qids[:5]:
            q = get_question_by_id(qid)
            if q:
                content = q.get("content") if hasattr(q, "get") else q["content"]
                results.append(f"ID {q['questionID']}: {content[:50]}...")
        summary = "\n".join(results)
        if len(qids) > 5:
            summary += f"\n... 共 {len(qids)} 条结果，仅显示前5条。"
        return f"通过笔记找到 {len(qids)} 道题目：\n{summary}"
    except Exception as e:
        trace("QuestionTools", f"{role} {user_id} SearchByNote Error", str(e), level="error")
        return f"根据笔记搜索题目时发生错误：{str(e)}"