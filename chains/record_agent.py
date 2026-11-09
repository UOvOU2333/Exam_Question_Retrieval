"""录题 Agent 对话主循环。

复用 deepseek_agent.run_agent 的 HTTP 调用/预算/去重/强制回答骨架，
替换工具集为录题 9 工具（RECORD_AGENT_TOOLS），
工具执行前做第三层权限校验（含物理控件拦截层），工具执行后写 tool_call 日志。
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
from chains.record_agent_perm import PermissionSwitches, check_tool_permission
from services.record_agent_auth_services import is_record_agent_enabled
from services.log_services import record_log
from utils.permissions import is_admin, has_permission

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"

# 大型录题任务可能持续很多轮，默认放开到较大值；可用环境变量覆盖。
# RECORD_AGENT_MAX_ITERATIONS：模型推理轮次上限
# RECORD_TOOL_CALL_BUDGET：累计工具调用预算，设为 0 或负数表示不限制
MAX_ITERATIONS = int(os.environ.get("RECORD_AGENT_MAX_ITERATIONS", "200"))
RECORD_TOOL_CALL_BUDGET = int(os.environ.get("RECORD_TOOL_CALL_BUDGET", "300"))
# 长会话优化：历史消息保留条数、单条工具结果进入上下文的字符上限、
# 最近多少条工具结果保留完整内容（更早的压缩，防止上下文无限膨胀）
MAX_HISTORY_MESSAGES = int(os.environ.get("RECORD_AGENT_MAX_HISTORY", "60"))
TOOL_RESULT_MAX_CHARS = int(os.environ.get("RECORD_AGENT_TOOL_RESULT_CHARS", "3000"))
KEEP_RECENT_TOOL_RESULTS = int(os.environ.get("RECORD_AGENT_KEEP_RECENT_TOOLS", "30"))


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
        "2. 草稿ID格式为 draft-N，与正式题号隔离。用户说'草稿一/草稿1/第一份草稿'时，\n"
        "   你必须将其解析为 draft-1 调用工具，禁止把'草稿一'映射为整数题号 1。\n"
        "3. 所有操作有记录、可撤销。\n\n"
        "草稿/题目 ID 引用规则：\n"
        "- 给草稿加备注用 add_note_to_draft 工具（target_draft_id 为 draft-N 字符串）\n"
        "- 给已入库题目加备注用 add_note_draft 工具（target_question_id 为整数）\n"
        "- 禁止把草稿编号当题目ID 传入，禁止混合使用\n\n"
        "可用工具（10 个）：\n"
        "- find_question：按年份/卷种/题号匹配题库已有题目，返回 questionID（只读查重）\n"
        "- create_question_draft：创建新题目草稿\n"
        "- update_question_draft：修改已有题目草稿（保存修改前快照）\n"
        "- add_note_draft：添加备注/标签/评分细则草稿（目标为已入库题目ID）\n"
        "- add_note_to_draft：为指定草稿添加备注（目标为草稿ID，备注随草稿一并提交）\n"
        "- insert_table_fragment：生成表格片段\n"
        "- insert_question_image：在题目中插入图片（需先在图片上传区上传）\n"
        "- pdf_upload_and_split：PDF 多题识别拆分\n"
        "- pdf_match_rubric：PDF 评分细则匹配题库题目\n"
        "- pdf_preview_fragment：预览 PDF 原文片段\n\n"
        f"工具调用约束：全程最多调用 {RECORD_TOOL_CALL_BUDGET} 次工具；达到预算后必须直接回答。\n\n"
        "回答要求：\n"
        "- 用简体中文回答\n"
        "- 生成草稿后告知草稿ID，提示用户在草稿列表确认\n"
        "- 识别题目时，先按年份(year)、卷种(paper_type)、题号(question_no)调用 find_question 匹配题库 questionID；\n"
        "  已存在题目时不要重复创建：用 update_question_draft 或告知用户该题已存在；只有未找到时才 create_question_draft。\n"
        "- 处理图片时，insert_question_image 的 file_id 必须是用户已上传的图片\n"
        "- 处理 PDF 时：PDF 每页已渲染为图片并上传，你在对话中能直接看到每页图片内容。\n"
        "  用视觉能力识别题目后，逐题调用 create_question_draft 生成草稿；\n"
        "  评分细则匹配时，视觉识别题号与细则文本后调用 pdf_match_rubric。\n"
        "  不依赖本地文本解析，以你看到的页面图片为准。\n"
        "  PDF 工具的 file_id 必须原样使用用户消息 [会话PDF] 中列出的真实值，禁止编造 local-pdf-1 之类的占位符。\n"
        "  评分细则匹配不需要事先提供题目 ID：识别细则后直接调用 pdf_match_rubric，工具会自动匹配题库候选题目；\n"
        "  不要用 add_note_draft 代替匹配流程。若 [当前批次] 没有提供页图，先请用户在 PDF 列表加载答案/细则所在页范围。\n"
        "  视觉识别细则时尽量提取年份(year)、卷种(paper_type)和题干关键词(question_hint)一并传入 rubrics，用于精准匹配。\n"
        "  调用 pdf_match_rubric 后，只转述工具实际返回的匹配草稿 ID 和数量；不要自行编造每条细则的来源、质量评估、相似度或处理建议。\n"
        "  匹配完成后提示用户：匹配草稿已生成，请在左侧草稿区的“评分细则匹配草稿”中查看并处理（覆盖/追加/跳过/丢弃）。\n"
        "备注/评分细则格式规范（参考已有备注）：\n"
        "  - 评分细则必须以【评分细则】开头；①②③④ 每个分点独占一行；保留原文措辞、赋分区间和评分点内容，不要概括改写。\n"
        "  - 等级量表必须用 Markdown 表格：| 等级 | 评分点1 | 评分点2 | 评分点3 | 评分点4 |，行依次为水平4/3/2/1；不要把四个水平堆在一行用“／”分隔。\n"
        "  - 原文有【超越下水示例】则保留在末尾；没有不要编造。\n"
        "- 严禁编造题目内容，基于你看到的图片/PDF页面图片/文本生成草稿\n"
        "- 题型(question_type)和知识模块(knowledge_modules)只能用系统已有合法值，\n"
        "  不可编造新类型。知识模块合法值：必修一/必修二/必修三/必修四/选必一/选必二/选必三。\n"
        "  知识模块按材料主旨判断，可多选，多项用英文逗号分隔：\n"
        "  必修一=中国特色社会主义；必修二=经济与社会；必修三=政治与法治；必修四=哲学与文化；\n"
        "  选必一=当代国际政治与经济；选必二=法律与生活；选必三=逻辑与思维\n"
        "  注意区分易混项：经济/市场/分配类选必修二，政治制度/依法治国/基层治理类选必修三，\n"
        "  哲学/文化/价值观类选必修四，国际关系/外交/国际组织类选选必一，\n"
        "  民事/合同/侵权/婚姻继承类选选必二，概念/判断/推理/逻辑规律类选选必三\n"
        "- 添加备注时 type_name 必须匹配备注类型表已有类型（如'评分细则'、'其他版本解析'），\n"
        "  不可编造新备注类型\n"
        "- 题目正文格式规范（选择题必须严格遵守）：\n"
        "  1) 正文开头不要写题号（如'1.'、'1、'、'第1题'），题号放 question_no 字段\n"
        "  2) 题干（含材料）中保留一个全角空括号'（ ）'供填答案；选项行末尾禁止再出现'（ ）'\n"
        "  3) 普通选项每项独占一行，形如：\n"
        "     A.门店违约，需双倍返还定金\n"
        "     B.刘某违约，不可主张返还定金\n"
        "     C.双方均违约，但均可免除违约责任\n"
        "     D.双方均不违约，均无需承担违约责任\n"
        "  4) 组合型选项（每项仅为①②③④的组合）可排成一行，选项间用空格分隔，形如：\n"
        "     A.①③ B.①④ C.②③ D.②④\n"
        "  5) 判断题干表述的①②③④每条独占一行，紧跟题干之后、选项之前"
    )


def _shrink_tool_messages(messages,
                          keep_recent=KEEP_RECENT_TOOL_RESULTS,
                          old_max_chars=500):
    """压缩较早的工具结果，控制长任务上下文体积。

    最近 keep_recent 条工具结果保持完整，更早的只保留前 old_max_chars 字符。
    """
    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    cutoff = len(tool_indices) - keep_recent
    if cutoff <= 0:
        return
    for idx in tool_indices[:cutoff]:
        content = messages[idx].get("content") or ""
        if len(content) > old_max_chars:
            messages[idx]["content"] = content[:old_max_chars] + "\n…[较早的工具结果已省略]"


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
    perm_switches=None,
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
    history_tail = history or []
    if MAX_HISTORY_MESSAGES > 0:
        history_tail = history_tail[-MAX_HISTORY_MESSAGES:]
    for m in history_tail:
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
        budget_reached = RECORD_TOOL_CALL_BUDGET > 0 and tool_call_count >= RECORD_TOOL_CALL_BUDGET
        force_answer = iteration >= MAX_ITERATIONS - 2 or budget_reached
        _shrink_tool_messages(working)
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

                # 物理权限控件拦截（白名单后、tool_call_count+=1 前；不消耗预算）
                if perm_switches is not None:
                    _allowed, _reason, _sname = check_tool_permission(tname, perm_switches)
                    if not _allowed:
                        result = "【操作已被禁用】%s，请在页面权限控件中开启。" % (_sname or _reason)
                        record_log(
                            operator="agent:%s" % (user_id or "?"),
                            case_id=None,
                            action="permission_denied",
                            detail={"layer": "tool_guard", "reason": _reason,
                                    "switch_name": _sname, "tool": tname,
                                    "args_preview": str(targs)[:200]},
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
                working.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result[:TOOL_RESULT_MAX_CHARS],
                })
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
