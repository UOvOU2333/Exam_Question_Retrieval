"""录题 Agent 对话主循环。

复用 deepseek_agent.run_agent 的 HTTP 调用/预算/去重/强制回答骨架，
替换工具集为录题 8 工具（RECORD_AGENT_TOOLS），
工具执行前做第三层权限校验，工具执行后写 tool_call 日志。
"""
import json
import os
import requests
from datetime import datetime

from chains.record_agent_tools import (
    RECORD_AGENT_TOOLS,
    RECORD_AGENT_TOOL_NAMES,
    RecordToolContext,
    _execute_record_tool,
)
from services.record_agent_auth_services import is_record_agent_enabled
from services.log_services import record_log
from utils.permissions import is_admin, has_permission

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"
MAX_ITERATIONS = 25
RECORD_TOOL_CALL_BUDGET = 15


def get_api_key() -> str | None:
    """API Key 仅服务端读取，不前端暴露。"""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("deepseek_api_key")
    except Exception:
        return None


def _build_record_system_prompt() -> str:
    """录题 Agent 系统提示。"""
    return (
        "你是高中政治题库录题助手，通过调用工具帮助用户录入题目、添加备注、处理 PDF。\n\n"
        "核心规则：\n"
        "1. 你生成的所有内容都是草稿，不会直接写入数据库。用户需要在页面确认后才正式提交。\n"
        "2. 草稿ID格式为 draft-N，与正式题号隔离，不会改错题号。\n"
        "3. 所有操作有记录、可撤销。\n\n"
        "可用工具（8 个）：\n"
        "- create_question_draft：创建新题目草稿\n"
        "- update_question_draft：修改已有题目草稿（保存修改前快照）\n"
        "- add_note_draft：添加备注/标签/评分细则草稿\n"
        "- insert_table_fragment：生成表格片段\n"
        "- insert_question_image：在题目中插入图片（需先在图片上传区上传）\n"
        "- pdf_upload_and_split：PDF 多题识别拆分\n"
        "- pdf_match_rubric：PDF 评分细则匹配题库题目\n"
        "- pdf_preview_fragment：预览 PDF 原文片段\n\n"
        f"工具调用约束：全程最多调用 {RECORD_TOOL_CALL_BUDGET} 次工具；达到预算后必须直接回答。\n\n"
        "回答要求：\n"
        "- 用简体中文回答\n"
        "- 生成草稿后告知草稿ID，提示用户在草稿列表确认\n"
        "- 处理图片时，insert_question_image 的 file_id 必须是用户已上传的图片\n"
        "- 处理 PDF 时：PDF 每页已渲染为图片并上传，你在对话中能直接看到每页图片内容。\n"
        "  用视觉能力识别题目后，逐题调用 create_question_draft 生成草稿；\n"
        "  评分细则匹配时，视觉识别题号与细则文本后调用 pdf_match_rubric。\n"
        "  不依赖本地文本解析，以你看到的页面图片为准。\n"
        "- 严禁编造题目内容，基于你看到的图片/PDF页面图片/文本生成草稿"
    )


def run_record_agent(
    history,
    user_input,
    api_key,
    base_url=DEFAULT_BASE_URL,
    model=DEFAULT_MODEL,
    user_role=None,
    user_id=None,
    session_id=None,
    draft_store=None,
    undo_stack=None,
    image_gallery=None,
    pdf_library=None,
    fragment_store=None,
    match_store=None,
    pdf_local_paths=None,
    image_file_ids=None,
):
    """运行录题 Agent。

    Args:
        history: [{"role", "content"}, ...]（不含 system）
        user_input: 用户输入
        api_key: DeepSeek API Key
        其余为各存储句柄与用户信息
        image_file_ids: 本次对话要引用的图片 file_id 列表（Files API 上传的），
            将以 {"type": "file", "file_id": ...} 内容块附在 user message 后，
            使 LLM 能理解图片内容。仅传 file-api- 开头的图片 file_id。

    Returns:
        tuple[str, list[dict], list[dict]]: (answer, steps, draft_previews)
        draft_previews 含本轮新增草稿预览
    """
    # 第二层权限校验（API 调用层）
    if not is_admin(user_role) and not is_record_agent_enabled(user_id):
        record_log(
            operator="agent:%s" % (user_id or "?"),
            case_id=None,
            action="permission_denied",
            detail={"layer": "api", "reason": "未授权使用录题 Agent", "user_id": user_id},
            session_id=session_id,
        )
        return "您未授权使用录题 Agent，请联系管理员授权。", [], []

    headers = {"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"}
    url = "%s/chat/completions" % base_url.rstrip("/")
    steps = []

    # 记录本轮草稿数（用于计算新增）
    pre_draft_count = len(draft_store.list_all()) if draft_store else 0
    pre_match_count = len(match_store.list_all()) if match_store else 0

    ctx = RecordToolContext(
        user_id=user_id,
        user_role=user_role,
        session_id=session_id,
        draft_store=draft_store,
        undo_stack=undo_stack,
        image_gallery=image_gallery,
        pdf_library=pdf_library,
        fragment_store=fragment_store,
        match_store=match_store,
        pdf_local_paths=pdf_local_paths,
    )

    working = [{"role": "system", "content": _build_record_system_prompt()}]
    for m in history:
        working.append({"role": m["role"], "content": m["content"]})
    # 构建 user message：若有图片引用，用 content 块数组让 LLM 理解图片内容
    # （DeepSeek Files API 通过 {"type": "file", "file_id": ...} 引用已上传图片）
    valid_image_ids = [fid for fid in (image_file_ids or []) if str(fid).startswith("file-api-")]
    if valid_image_ids:
        user_content = [{"type": "text", "text": user_input}]
        for fid in valid_image_ids:
            user_content.append({"type": "file", "file_id": fid})
        working.append({"role": "user", "content": user_content})
    else:
        working.append({"role": "user", "content": user_input})

    tool_call_count = 0
    last_tool_signature = None

    for iteration in range(MAX_ITERATIONS):
        force_answer = iteration >= MAX_ITERATIONS - 2 or tool_call_count >= RECORD_TOOL_CALL_BUDGET
        payload = {"model": model, "messages": working, "stream": False}
        if not force_answer:
            payload["tools"] = RECORD_AGENT_TOOLS
        if force_answer and tool_call_count > 0:
            payload["messages"] = working + [{
                "role": "user",
                "content": "请基于以上已生成的草稿直接给出最终回答，不要再调用工具。提示用户在草稿列表确认提交。",
            }]
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
        except requests.RequestException as e:
            steps.append({"error": "网络请求失败: %s" % e})
            return "网络请求失败，请检查网络连接和 API 地址。", steps, []

        if resp.status_code != 200:
            steps.append({"error": "HTTP %d: %s" % (resp.status_code, resp.text[:300])})
            return "调用 AI 服务失败（HTTP %d），请检查 API Key、模型名与网络。" % resp.status_code, steps, []

        try:
            data = resp.json()
            msg = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError) as e:
            steps.append({"error": "解析响应失败: %s" % e})
            return "AI 服务返回数据异常。", steps, []

        working.append({
            "role": "assistant",
            "content": msg.get("content"),
            "tool_calls": msg.get("tool_calls"),
        })

        tool_calls = msg.get("tool_calls")
        if tool_calls and not force_answer:
            for tc in tool_calls:
                fn = tc["function"]
                tname = fn["name"]
                try:
                    targs = json.loads(fn["arguments"] or "{}")
                except json.JSONDecodeError:
                    targs = {}
                signature = (tname, json.dumps(targs, sort_keys=True))
                if signature == last_tool_signature:
                    steps.append({"tool": tname, "args": targs, "result": "跳过：与上一次调用完全相同"})
                    working.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": "已跳过重复调用，请直接基于已有结果回答。",
                    })
                    continue
                last_tool_signature = signature

                # 第三层权限校验（工具执行层）
                if tname not in RECORD_AGENT_TOOL_NAMES:
                    result = "工具 %s 不在录题 Agent 工具白名单内" % tname
                    record_log(
                        operator="agent:%s" % (user_id or "?"),
                        case_id=None,
                        action="permission_denied",
                        detail={"layer": "tool", "reason": "tool_not_whitelisted", "tool": tname},
                        session_id=session_id,
                    )
                    steps.append({"tool": tname, "args": targs, "result": result})
                    working.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                    continue

                tool_call_count += 1
                result = _execute_record_tool(tname, targs, ctx)
                # 写 tool_call 日志
                record_log(
                    operator="agent:%s" % (user_id or "?"),
                    case_id=targs.get("target_question_id"),
                    action="tool_call",
                    detail={"tool": tname, "args_preview": str(targs)[:500]},
                    session_id=session_id,
                )
                steps.append({"tool": tname, "args": targs, "result": result[:1500]})
                working.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            continue

        answer = msg.get("content") or ""
        # 计算本轮新增草稿预览
        draft_previews = _collect_new_drafts(draft_store, match_store, pre_draft_count, pre_match_count)
        return answer, steps, draft_previews

    draft_previews = _collect_new_drafts(draft_store, match_store, pre_draft_count, pre_match_count)
    return "已达最大推理轮次，未能生成最终回答，请尝试换一种问法。", steps, draft_previews


def _collect_new_drafts(draft_store, match_store, pre_draft_count, pre_match_count):
    """收集本轮新增的草稿/匹配草稿预览。"""
    previews = []
    if draft_store:
        all_drafts = draft_store.list_all()
        for d in all_drafts[pre_draft_count:]:
            previews.append({
                "type": "draft",
                "draft_id": d["draft_id"],
                "draft_type": d["draft_type"],
                "status": d["status"],
            })
    if match_store:
        all_matches = match_store.list_all()
        for m in all_matches[pre_match_count:]:
            previews.append({
                "type": "match",
                "match_id": m["match_id"],
                "status": m["status"],
                "confidence": m["confidence"],
                "matched_question_id": m["matched_question_id"],
            })
    return previews
