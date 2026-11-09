# pages/recordAgentPage.py
"""录题助手主页面。

三层权限校验（页面层）：
  1. require_permission('record_agent')
  2. is_record_agent_enabled(user_id)
  3. has_permission(role, 'upload')
任一未通过写 permission_denied 日志并拒绝。

安全核心——确认提交三段式：
  草稿（session_state）→ 用户确认 → 服务层写库（事务 + 撤销栈 + 日志）
  工具执行层禁直写，仅生成草稿。

布局（仿照试题更新页）：
  顶部：历史会话 expander（恢复/新建）| Agent 权限控件 expander
  上传文件：权限控件之下（expander）
  标题行：录题助手（左）| 草稿编号 number_input（右）——同 updatePage 题号位置
  双栏：左侧手动修改区/预览区（标题与草稿编号之间有切换按钮）| 右侧助手对话历史
  预览：切换后手动修改区变为预览区，用 render_markdown 渲染选中草稿
  操作记录：双栏之下，简洁摘要 + 完整细节 expander
  撤销栈：操作记录之下
  匹配确认：有匹配草稿时显示
  chat_input：页面最底部（Streamlit 硬性限制）

PDF 处理：
  上传 PDF 不限制页数（仅文件大小 ≤100MiB），只保存本地并读取页数；
  用户在 PDF 列表选择页范围分批渲染（默认覆盖到最大页号，支持非连续页号），
  只渲染上传所选页图并传给 Agent。已处理页记录在会话状态中。

会话历史：
  关键操作前后把 session_state 快照写入 record_agent_sessions 表；
  恢复时检测文件是否超过 24 小时未使用以及本地 PDF 是否存在，
  过期文件清空引用并提示重新上传或重新加载批次。
"""
import streamlit as st
import os
import uuid
import json
from datetime import datetime

from utils.auth_utils import require_permission
from utils.permissions import has_permission, is_admin
from services.record_agent_auth_services import is_record_agent_enabled
from services.log_services import record_log, get_session_logs
from services.question_services import (
    create_question,
    update_question,
    move_to_recycle_bin,
    get_question_by_id,
    get_question_by_no_and_paper,
)
from services.note_services import (
    create_question_note,
    soft_delete_question_note,
    get_all_note_types,
    get_visible_note_type_ids,
    get_note_type_by_name,
    get_note_type,
    get_question_notes,
)
from chains.record_agent import run_record_agent, get_api_key
from chains.note_format import normalize_rubric_content
from services.record_session_services import (
    build_snapshot,
    save_session,
    list_sessions,
    restore_session,
)
from chains.record_agent_perm import PermissionSwitches, OP_TYPE_LABELS
from chains.record_agent_drafts import (
    DraftStore,
    UndoStack,
    SessionImageGallery,
    SessionPdfLibrary,
    PdfFragmentStore,
    MatchDraftStore,
)
from chains.record_agent_files import (
    upload_to_files_api,
    delete_file_api,
    validate_image,
    validate_pdf,
    save_pdf_to_local,
    remove_local_pdf,
    upload_pdf_pages_as_images,
    delete_page_images,
    cleanup_local_cache,
    download_to_local_cache,
    FILE_EXPIRE_SECONDS,
)
from chains.pdf_to_images import get_pdf_page_count, parse_page_selection, PdfRenderError
from utils.render_utils import render_markdown
from utils.multi_func import rich_markdown
from utils.note_utils import display_notes_list, compact_note_type_selector
from tools.exam_type_utils import QUESTION_TYPES, KNOWLEDGE_MODULES

IMAGE_DIR = "static/images/questions"
os.makedirs(IMAGE_DIR, exist_ok=True)


def _batch_pages(batch):
    """取批次页号列表，兼容旧版 start/end 结构。"""
    pages = batch.get("pages")
    if pages:
        return [int(p) for p in pages]
    if batch.get("start") is not None and batch.get("end") is not None:
        return list(range(int(batch["start"]), int(batch["end"]) + 1))
    return []


def _format_page_ranges(page_nos):
    """把页号列表压缩成区间字符串，如 '1-30,45-60'。"""
    pages = sorted({int(n) for n in page_nos or []})
    if not pages:
        return ""
    parts = []
    start = prev = pages[0]
    for page_no in pages[1:]:
        if page_no == prev + 1:
            prev = page_no
            continue
        parts.append("%d-%d" % (start, prev) if start != prev else str(start))
        start = prev = page_no
    parts.append("%d-%d" % (start, prev) if start != prev else str(start))
    return ",".join(parts)


_ACTION_LABELS = {
    "tool_call": "工具调用",
    "draft_create": "创建草稿",
    "draft_discard": "丢弃草稿",
    "pdf_upload": "上传PDF",
    "image_upload": "上传图片",
    "commit": "提交",
    "undo": "撤销",
    "rubric_upload": "上传细则",
    "rubric_match": "细则匹配",
    "rubric_match_revise": "修正匹配",
    "rubric_match_resolve": "细则处理",
    "rubric_split": "细则拆分",
    "pdf_split": "PDF拆分",
    "permission_denied": "拒绝访问",
    "permission_toggle": "权限切换",
}


@st.dialog("确认紧急停止")
def _confirm_emergency_stop(switches, user_id, sid):
    """紧急停止二次确认：中断 AI 会话并禁止 Agent 所有工具操作。"""
    st.warning("将立即中断当前 AI 会话，并禁止 Agent 的所有工具操作。")
    c1, c2 = st.columns(2)
    if c1.button("确认停止", type="primary", key="ra_stop_confirm"):
        switches.set_emergency_stop(True)
        record_log(operator="user:%s" % user_id, case_id=None,
                   action="permission_toggle",
                   detail={"switch": "emergency_stop", "before": False, "after": True},
                   session_id=sid)
        st.rerun()
    if c2.button("取消", key="ra_stop_cancel"):
        st.rerun()


@st.dialog("恢复运行")
def _confirm_resume_agent(switches, user_id, sid):
    """恢复运行二次确认。"""
    st.info("确认后将恢复 Agent 运行与工具操作。")
    c1, c2 = st.columns(2)
    if c1.button("确认恢复", type="primary", key="ra_resume_confirm"):
        switches.set_emergency_stop(False)
        record_log(operator="user:%s" % user_id, case_id=None,
                   action="permission_toggle",
                   detail={"switch": "emergency_stop", "before": True, "after": False},
                   session_id=sid)
        st.rerun()
    if c2.button("取消", key="ra_resume_cancel"):
        st.rerun()


def _render_perm_controls(switches, user_id, sid):
    """渲染 Agent 权限控件 expander（7 个操作粒度开关；紧急停止按钮在标题行）。"""
    with st.expander("Agent 权限控件", expanded=not switches.is_default()):
        st.caption("操作粒度开关")
        cur_sw = switches.get_all()
        cols = st.columns(2)
        for i, (op_type, label) in enumerate(OP_TYPE_LABELS.items()):
            with cols[i % 2]:
                cur_val = cur_sw.get(op_type, True)
                new_val = st.checkbox(label, value=cur_val, key="ra_perm_%s_%s" % (op_type, sid))
                if new_val != cur_val:
                    switches.set_switch(op_type, new_val)
                    record_log(operator="user:%s" % user_id, case_id=None,
                               action="permission_toggle",
                               detail={"switch": op_type, "before": cur_val, "after": new_val},
                               session_id=sid)


def _summarize_detail(action, detail):
    """从 detail 提取最简关键字段作摘要，不泄露 JSON。"""
    if not detail or isinstance(detail, str):
        return ""
    if action == "tool_call":
        return detail.get("tool", "") or detail.get("upload", "")
    if action in ("draft_create", "draft_discard"):
        return detail.get("draft_id", "")
    if action == "pdf_upload":
        return "%s (%s页)" % (detail.get("filename", ""), detail.get("pages", ""))
    if action == "image_upload":
        return detail.get("filename", "") or detail.get("file_id", "")
    if action == "commit":
        return detail.get("draft_id", "") or ("题%s" % detail.get("qid", ""))
    if action == "undo":
        return detail.get("op_type", "")
    if action in ("rubric_upload", "rubric_match_revise"):
        return detail.get("match_id", "")
    if action == "permission_denied":
        return detail.get("reason", "")
    return ""


def _render_operation_logs(sid):
    """外层 markdown 表格简约摘要；expander 内逐行完整 `时间 | 操作者 | 动作 | {json}`。"""
    logs = get_session_logs(sid, limit=50)
    if not logs:
        st.caption("暂无操作记录")
        return
    table = ["| 时间 | 角色 | 动作 | 摘要 |", "|------|------|------|------|"]
    for log in logs:
        time_short = (log.get("created_at") or "")[11:19]
        action = log.get("action", "")
        action_cn = _ACTION_LABELS.get(action, action)
        operator = (log.get("operator") or "").replace("user:", "用户").replace("agent", "AI")
        summary = _summarize_detail(action, log.get("detail"))
        table.append("| %s | %s | %s | %s |" % (time_short, operator, action_cn, summary))
    st.markdown("\n".join(table))
    with st.expander("完整记录详情", expanded=False):
        detail_lines = []
        for log in logs:
            time_short = (log.get("created_at") or "")[11:19]
            operator = log.get("operator") or ""
            action = log.get("action", "")
            detail = log.get("detail")
            detail_json = json.dumps(detail, ensure_ascii=False) if detail else ""
            detail_lines.append("%s | %s | %s | %s" % (time_short, operator, action, detail_json))
        st.code("\n".join(detail_lines), language="text")


def _collect_edit_snapshot(d):
    """从 session_state 读取当前编辑控件值，供切换预览前自动保存。

    预览模式下输入控件不再渲染，Streamlit 会在本轮结束时清理其状态，
    因此切换前先把控件值写入草稿，避免切回编辑时丢失未保存的修改。
    """
    did = d["draft_id"]
    snap = {}

    if d["draft_type"] == "add_note":
        target = st.session_state.get("ra_note_target_%s" % did)
        type_name = st.session_state.get("ra_note_type_%s" % did)
        content = st.session_state.get("ra_note_content_%s" % did)
        if target is not None:
            snap["target_question_id"] = int(target) if target else None
        if type_name is not None:
            note_type = get_note_type_by_name(type_name)
            snap["type_name"] = type_name
            snap["type_id"] = note_type["id"] if note_type else None
        if content is not None:
            snap["content"] = content
        return snap

    text_fields = (
        ("content", "ra_edit_content_%s"),
        ("answer", "ra_edit_answer_%s"),
        ("analysis", "ra_edit_analysis_%s"),
        ("year", "ra_edit_year_%s"),
        ("paper_type", "ra_edit_pt_%s"),
        ("question_no", "ra_edit_qno_%s"),
    )
    for field, key_tpl in text_fields:
        value = st.session_state.get(key_tpl % did)
        if value is not None:
            snap[field] = value

    question_type = st.session_state.get("ra_edit_qt_%s" % did)
    if question_type is not None:
        snap["question_type"] = "" if question_type == "（未选择）" else question_type

    knowledge_modules = st.session_state.get("ra_edit_km_%s" % did)
    if knowledge_modules is not None:
        snap["knowledge_modules"] = ",".join(knowledge_modules)

    return snap


def _render_draft_preview(d):
    """渲染草稿快照（预览模式，替代手动修改区的输入控件）。"""
    snapshot = d.get("snapshot_after", {})

    if d["draft_type"] == "add_note":
        st.markdown("### 备注内容")
        content = snapshot.get("content", "") or ""
        if content.strip():
            render_markdown(content)
        else:
            st.info("备注内容为空")
        return

    meta = []
    for label, field in (
        ("年份", "year"), ("卷种", "paper_type"), ("题号", "question_no"),
        ("题型", "question_type"), ("知识模块", "knowledge_modules"),
    ):
        value = snapshot.get(field, "")
        if value:
            meta.append("%s：%s" % (label, value))
    if meta:
        st.caption(" | ".join(meta))

    has_any = False
    for label, field in (("题目内容", "content"), ("答案", "answer"), ("解析", "analysis")):
        value = snapshot.get(field, "") or ""
        if value.strip():
            st.markdown("### %s" % label)
            render_markdown(value)
            has_any = True
    if not has_any:
        st.info("草稿内容为空")


def _render_note_section(d, draft_store, user_id, sid):
    """备注栏目：展示草稿携带的备注 + 已有题目备注。

    - 草稿携带备注（snapshot.notes）：提交时一并写入，优先展示
    - update_question 草稿：额外展示 target_question_id 已有备注
    - 无任何备注：显示"暂无备注"
    """
    cur_dtype = d["draft_type"]
    target_qid = d.get("target_question_id")

    st.subheader("题目备注")

    carried = d.get("snapshot_after", {}).get("notes", [])
    if carried:
        st.caption("草稿携带备注 %d 条（提交时一并写入）" % len(carried))
        for n in carried:
            st.write("**%s**" % n.get("type_name", ""))
            render_markdown(n.get("content", ""))

    if cur_dtype == "update_question" and target_qid:
        if carried:
            st.caption("题目已有备注")
        display_notes_list(target_qid)
    elif not carried:
        st.info("暂无备注")


def record_agent_page():
    """录题助手主页面入口。"""
    # ===== 第一层权限校验（页面层）=====
    require_permission("record_agent")
    user_id = st.session_state.get("user_id")
    user_role = st.session_state.get("role")
    username = st.session_state.get("username", "")

    if not is_record_agent_enabled(user_id):
        record_log(
            operator="user:%s" % user_id,
            case_id=None,
            action="permission_denied",
            detail={"layer": "page", "reason": "未授权录题助手"},
        )
        st.error("您未授权使用录题助手，请联系管理员授权。")
        st.stop()
    if not has_permission(user_role, "upload"):
        record_log(
            operator="user:%s" % user_id,
            case_id=None,
            action="permission_denied",
            detail={"layer": "page", "reason": "无 upload 权限"},
        )
        st.error("无权限访问")
        st.stop()

    # ===== 初始化会话状态 =====
    if "ra_session_id" not in st.session_state:
        cleanup_local_cache()
        st.session_state["ra_session_id"] = "ra_%s" % uuid.uuid4().hex[:8]
    if "ra_history" not in st.session_state:
        st.session_state["ra_history"] = []
    if "ra_pdf_local_paths" not in st.session_state:
        st.session_state["ra_pdf_local_paths"] = {}

    sid = st.session_state["ra_session_id"]
    draft_store = DraftStore(sid)
    undo_stack = UndoStack(sid)
    image_gallery = SessionImageGallery(sid)
    pdf_library = SessionPdfLibrary(sid)
    fragment_store = PdfFragmentStore(sid)
    match_store = MatchDraftStore(sid)
    perm_switches = PermissionSwitches(sid)

    # ===== 会话持久化辅助 =====
    def _session_title():
        """用首条用户指令前 20 字作为历史会话标题。"""
        for message in st.session_state.get("ra_history", []):
            if message.get("role") == "user" and (message.get("content") or "").strip():
                return message["content"].strip()[:20]
        return "会话 %s" % sid

    def _persist():
        """把当前会话状态写入历史记录（无实际内容的空会话不保存）。"""
        snapshot = build_snapshot(st.session_state, sid)
        has_content = bool(snapshot.get("ra_history")) or any(snapshot.get(key) for key in (
            "record_drafts_%s" % sid, "record_images_%s" % sid,
            "record_pdfs_%s" % sid, "record_matches_%s" % sid,
        ))
        if not has_content:
            return
        try:
            save_session(sid, user_id, _session_title(), snapshot)
        except Exception:
            # 历史保存失败不阻断主流程
            pass

    def _save_and_rerun():
        _persist()
        st.rerun()

    # ===== 标题行：左标题/会话信息，右侧历史会话入口与紧急停止 =====
    pending_drafts = draft_store.list_pending()
    title_col, history_col, stop_col = st.columns([2.4, 1, 1])
    with title_col:
        st.title("录题助手")
        st.caption("当前用户：%s | 会话：%s" % (username, sid))
    with history_col:
        with st.popover("历史会话"):
            history_rows = list_sessions(user_id)
            if history_rows:
                history_labels = [
                    "%s | %s | 草稿%d条 | 对话%d条 | %s" % (
                        row["sid"], (row["updated_at"] or "")[:19],
                        row["drafts"], row["messages"], row["title"],
                    )
                    for row in history_rows
                ]
                label_by_sid = {
                    row["sid"]: label for row, label in zip(history_rows, history_labels)
                }
                pick_sid = st.selectbox(
                    "选择要恢复的会话", options=list(label_by_sid.keys()),
                    format_func=lambda sid: label_by_sid[sid], key="ra_history_pick",
                )
                if st.button("恢复会话", key="ra_history_restore"):
                    _persist()
                    restored, warnings = restore_session(
                        st.session_state, pick_sid, user_id
                    )
                    if restored is None:
                        st.error("会话不存在或无权访问")
                    else:
                        st.session_state["ra_restore_warnings"] = warnings
                        st.rerun()
            else:
                st.caption("暂无历史会话")
            if st.button("新建会话", key="ra_history_new"):
                _persist()
                st.session_state["ra_session_id"] = "ra_%s" % uuid.uuid4().hex[:8]
                st.session_state["ra_history"] = []
                st.session_state["ra_pdf_local_paths"] = {}
                st.session_state.pop("ra_active_batch", None)
                st.session_state.pop("ra_restore_warnings", None)
                st.rerun()
    with stop_col:
        if perm_switches.get_emergency_stop():
            st.caption("已紧急停止")
            if st.button("恢复运行", key="ra_emergency_resume", use_container_width=True):
                _confirm_resume_agent(perm_switches, user_id, sid)
        else:
            if st.button("紧急停止", type="primary", key="ra_emergency_stop",
                         use_container_width=True):
                _confirm_emergency_stop(perm_switches, user_id, sid)

    # ===== 历史会话恢复提示 =====
    restore_warnings = st.session_state.pop("ra_restore_warnings", None)
    if restore_warnings:
        st.warning("历史会话已恢复，但以下文件已过期：\n"
                   + "\n".join("- %s" % w for w in restore_warnings))

    # ===== 顶部：Agent 权限控件 =====
    _render_perm_controls(perm_switches, user_id, sid)

    # ===== 上传文件 =====
    with st.expander("上传文件", expanded=False):
        col_img, col_pdf = st.columns(2)
        with col_img:
            st.caption("图片上传（JPEG/PNG/GIF/WebP，≤64MiB）")
            img_files = st.file_uploader(
                "上传图片",
                type=["jpeg", "jpg", "png", "gif", "webp"],
                accept_multiple_files=True,
                key="ra_img_upload_%s" % sid,
                label_visibility="collapsed",
            )
            if img_files:
                api_key = get_api_key()
                if not api_key:
                    st.error("DeepSeek API Key 未配置")
                else:
                    for f in img_files:
                        fbytes = f.getvalue()
                        file_sig = "ra_img_done_%s_%d" % (f.name, len(fbytes))
                        if st.session_state.get(file_sig):
                            continue
                        ok, msg = validate_image(f.name, fbytes)
                        if not ok:
                            st.error("%s: %s" % (f.name, msg))
                            continue
                        try:
                            file_id = upload_to_files_api(fbytes, f.name, api_key=api_key)
                            image_gallery.add(file_id, f.name, len(fbytes))
                            record_log(operator="user:%s" % user_id, case_id=None,
                                       action="tool_call", detail={"upload": "image", "file_id": file_id},
                                       session_id=sid)
                            st.session_state[file_sig] = True
                            st.success("已上传: %s" % f.name)
                        except Exception as e:
                            st.error("上传失败 %s: %s" % (f.name, e))
        with col_pdf:
            st.caption("PDF 上传（≤100MiB，每页转图片上传由 AI 视觉识别）")
            pdf_files = st.file_uploader(
                "上传 PDF",
                type=["pdf"],
                accept_multiple_files=True,
                key="ra_pdf_upload_%s" % sid,
                label_visibility="collapsed",
            )
            if pdf_files:
                api_key = get_api_key()
                if not api_key:
                    st.error("DeepSeek API Key 未配置")
                else:
                    for f in pdf_files:
                        fbytes = f.getvalue()
                        file_sig = "ra_pdf_done_%s_%d" % (f.name, len(fbytes))
                        if st.session_state.get(file_sig):
                            continue
                        ok, msg = validate_pdf(f.name, fbytes)
                        if not ok:
                            st.error("%s: %s" % (f.name, msg))
                            continue
                        try:
                            local_file_id, local_path = save_pdf_to_local(fbytes, f.name)
                            st.session_state["ra_pdf_local_paths"][local_file_id] = local_path
                            page_count = get_pdf_page_count(local_path)
                            pdf_library.add(
                                local_file_id, f.name, len(fbytes),
                                page_count, "multi_question",
                                page_file_ids=[],
                            )
                            record_log(
                                operator="user:%s" % user_id, case_id=None,
                                action="pdf_upload",
                                detail={"file_id": local_file_id, "filename": f.name,
                                        "pages": page_count},
                                session_id=sid,
                            )
                            st.session_state[file_sig] = True
                            st.success("已上传 PDF: %s（共 %d 页，请在 PDF 列表选择每批处理范围）" % (
                                f.name, page_count,
                            ))
                        except Exception as e:
                            st.error("上传失败 %s: %s" % (f.name, e))
        # 会话文件列表
        images = image_gallery.list_all()
        pdfs = pdf_library.list_all()
        if images:
            st.write("**图片**")
            for im in images:
                ic1, ic2 = st.columns([4, 1])
                ic1.write("%s | %s | %d bytes" % (im["filename"], im["file_id"], im["bytes_size"]))
                with ic2:
                    if st.button("删除", key="del_img_%s" % im["file_id"]):
                        delete_file_api(im["file_id"])
                        image_gallery.remove(im["file_id"])
                        _save_and_rerun()
        if pdfs:
            st.write("**PDF**")
            for pf in pdfs:
                fid = pf["file_id"]
                processed = pf.get("processed_pages", [])
                active = pf.get("active_pages", [])
                expired = pf.get("expired", False)
                info = "%s | %s | %d bytes | 共 %d 页 | 已处理 %d 页" % (
                    pf["filename"], fid, pf["bytes_size"], pf["page_count"], len(processed),
                )
                if processed:
                    info += "（%s）" % _format_page_ranges(processed)
                if active:
                    info += " | 当前批次 第 %s 页" % _format_page_ranges(active)
                if expired:
                    info += " | 页图已过期"
                pc1, pc2 = st.columns([4, 1])
                pc1.write(info)
                with pc2:
                    if st.button("删除", key="del_pdf_%s" % fid):
                        page_fids = pdf_library.remove(fid)
                        if page_fids:
                            delete_page_images(page_fids, api_key=get_api_key())
                        remove_local_pdf(fid, st.session_state["ra_pdf_local_paths"])
                        if st.session_state.get("ra_active_batch", {}).get("file_id") == fid:
                            st.session_state.pop("ra_active_batch", None)
                        _save_and_rerun()
                # 页选择：起始默认下一个未处理页，结束默认最大页号；支持非连续页号表达式
                next_page = max(processed) + 1 if processed else 1
                if next_page > pf["page_count"]:
                    next_page = 1
                b1, b2 = st.columns([1, 1])
                start = b1.number_input(
                    "起始页", min_value=1, max_value=pf["page_count"],
                    value=next_page, step=1, key="pdf_start_%s" % fid,
                )
                end = b2.number_input(
                    "结束页（默认最大页号）", min_value=1, max_value=pf["page_count"],
                    value=pf["page_count"], step=1, key="pdf_end_%s" % fid,
                )
                page_expr = st.text_input(
                    "自定义页号（可选，支持非连续，如 1-5,8,10-12；留空则使用起始-结束）",
                    value="", key="pdf_pages_%s" % fid,
                )
                b3, b4 = st.columns([1.5, 1.5])
                with b3:
                    if st.button("加载所选页图", key="pdf_batch_%s" % fid):
                        local_path = st.session_state["ra_pdf_local_paths"].get(fid)
                        page_nos = None
                        try:
                            if page_expr.strip():
                                page_nos = parse_page_selection(page_expr, pf["page_count"])
                            else:
                                if int(end) < int(start):
                                    raise PdfRenderError("结束页不能小于起始页")
                                page_nos = list(range(int(start), int(end) + 1))
                        except (PdfRenderError, ValueError) as e:
                            st.error("页选择无效：%s" % e)
                        if page_nos:
                            if not local_path or not os.path.exists(local_path):
                                st.error("本地 PDF 已过期，请重新上传该 PDF")
                            else:
                                api_key = get_api_key()
                                if not api_key:
                                    st.error("DeepSeek API Key 未配置")
                                else:
                                    try:
                                        page_map = pf.get("page_file_map", {}) or {}
                                        # 页图接近远端硬有效期时整体重传，避免复用即将失效的 file_id
                                        uploaded_at = pf.get("page_files_uploaded_at")
                                        if uploaded_at:
                                            try:
                                                uploaded_dt = datetime.fromisoformat(str(uploaded_at))
                                                if (datetime.now() - uploaded_dt).total_seconds() > FILE_EXPIRE_SECONDS - 3600:
                                                    pdf_library.clear_page_files(fid, expired=True)
                                                    page_map = {}
                                            except (ValueError, TypeError):
                                                pass
                                        missing = [p for p in page_nos if str(p) not in page_map]
                                        if missing:
                                            with st.spinner("正在渲染并上传 %d 页..." % len(missing)):
                                                page_files = upload_pdf_pages_as_images(
                                                    local_path, pf["filename"],
                                                    page_nos=missing, api_key=api_key,
                                                )
                                            pdf_library.add_page_files(fid, page_files)
                                        else:
                                            # 所选页图此前已上传（含已处理页），直接复用
                                            pdf_library.touch(fid)
                                        pdf_library.set_active_pages(fid, page_nos)
                                        for other in pdf_library.list_all():
                                            if other["file_id"] != fid:
                                                pdf_library.set_active_pages(other["file_id"], [])
                                        st.session_state["ra_active_batch"] = {
                                            "file_id": fid, "filename": pf["filename"],
                                            "pages": page_nos,
                                        }
                                        _save_and_rerun()
                                    except Exception as e:
                                        st.error("生成页图失败: %s" % e)
                        elif page_nos is not None:
                            st.error("请至少选择一页")
                with b4:
                    if active:
                        st.caption("当前批次：第 %s 页" % _format_page_ranges(active))
                        if st.button("取消当前批次", key="pdf_batch_clear_%s" % fid):
                            pdf_library.set_active_pages(fid, [])
                            st.session_state.pop("ra_active_batch", None)
                            _save_and_rerun()
                    else:
                        st.caption("页数不限，支持非连续页号；已处理页也可重新选择处理")

    # ===== 双栏：左侧手动修改区/预览区 | 右侧助手对话 =====
    edit_content = edit_answer = edit_analysis = None
    cur_dtype = None
    show_preview = bool(st.session_state.get("ra_show_preview", False))
    col_edit, col_chat = st.columns(2)

    # --- 左侧：手动修改区/预览区 ---
    with col_edit:
        col_title, col_draft = st.columns([2, 3])
        with col_title:
            st.subheader("预览区" if show_preview else "手改区")
        with col_draft:
            if pending_drafts:
                draft_idx = st.number_input(
                    "草稿编号（0不选，1~%d 选择草稿）" % len(pending_drafts),
                    min_value=0, max_value=len(pending_drafts), value=0, step=1,
                    key="ra_draft_sel",
                )
            else:
                st.info("暂无草稿")
                draft_idx = 0
        if st.button("预览" if not show_preview else "编辑",
                     key="ra_toggle_preview", use_container_width=True):
            # 切到预览前自动保存当前编辑内容，避免切回编辑时丢失
            if not show_preview and pending_drafts:
                cur_idx = int(st.session_state.get("ra_draft_sel", 0) or 0)
                if 0 < cur_idx <= len(pending_drafts):
                    pending_snap = _collect_edit_snapshot(pending_drafts[cur_idx - 1])
                    if pending_snap:
                        draft_store.update_snapshot(
                            pending_drafts[cur_idx - 1]["draft_id"], pending_snap
                        )
            st.session_state["ra_show_preview"] = not show_preview
            _save_and_rerun()
        if pending_drafts and int(draft_idx) > 0:
            d = pending_drafts[int(draft_idx) - 1]
            snapshot = d.get("snapshot_after", {})
            cur_dtype = d["draft_type"]
            st.caption("%s [%s]" % (d["draft_id"], cur_dtype))
            rich_markdown(IMAGE_DIR, True, None) if not show_preview else None
            snap_update = {}
            if show_preview:
                _render_draft_preview(d)
                if cur_dtype != "add_note":
                    _render_note_section(d, draft_store, user_id, sid)
            elif cur_dtype == "add_note":
                note_target = st.number_input(
                    "目标题目ID", value=snapshot.get("target_question_id") or 0, step=1,
                    key="ra_note_target_%s" % d["draft_id"],
                )
                all_types = get_all_note_types()
                if user_role and not is_admin(user_role):
                    visible_ids = set(get_visible_note_type_ids(user_role))
                    all_types = [t for t in all_types if t["id"] in visible_ids]
                type_names = [t["type_name"] for t in all_types]
                cur_tn = snapshot.get("type_name", "")
                tn_idx = type_names.index(cur_tn) if cur_tn in type_names else 0
                note_type_sel = st.selectbox(
                    "备注类型", options=type_names, index=tn_idx,
                    key="ra_note_type_%s" % d["draft_id"],
                )
                edit_content = st.text_area(
                    "备注内容", value=snapshot.get("content", ""), height=200,
                    key="ra_note_content_%s" % d["draft_id"],
                )
                nt = get_note_type_by_name(note_type_sel)
                snap_update = {
                    "target_question_id": int(note_target) if note_target else None,
                    "type_id": nt["id"] if nt else None,
                    "type_name": note_type_sel,
                    "content": edit_content,
                }
            else:
                edit_content = st.text_area("题目正文", value=snapshot.get("content", ""), height=150,
                                            key="ra_edit_content_%s" % d["draft_id"])
                edit_answer = st.text_area("答案", value=snapshot.get("answer", ""), height=80,
                                           key="ra_edit_answer_%s" % d["draft_id"])
                edit_analysis = st.text_area("解析", value=snapshot.get("analysis", ""), height=100,
                                             key="ra_edit_analysis_%s" % d["draft_id"])
                year = st.text_input("年份", value=snapshot.get("year", ""), key="ra_edit_year_%s" % d["draft_id"])
                paper_type = st.text_input("卷种", value=snapshot.get("paper_type", ""), key="ra_edit_pt_%s" % d["draft_id"])
                question_no = st.text_input("题号", value=snapshot.get("question_no", ""), key="ra_edit_qno_%s" % d["draft_id"])
                type_options = ["（未选择）"] + QUESTION_TYPES
                qt_val = snapshot.get("question_type", "")
                qt_idx = type_options.index(qt_val) if qt_val in type_options else 0
                question_type_sel = st.selectbox("题型", options=type_options, index=qt_idx, key="ra_edit_qt_%s" % d["draft_id"])
                question_type = None if question_type_sel == "（未选择）" else question_type_sel
                km_str = snapshot.get("knowledge_modules", "")
                km_list = [k.strip() for k in km_str.split(",") if k.strip()] if km_str else []
                default_km = [k for k in km_list if k in KNOWLEDGE_MODULES]
                knowledge_modules = st.multiselect("知识模块", options=KNOWLEDGE_MODULES,
                                                   default=default_km, key="ra_edit_km_%s" % d["draft_id"])
                snap_update = {
                    "content": edit_content, "answer": edit_answer, "analysis": edit_analysis,
                    "year": year, "paper_type": paper_type, "question_no": question_no,
                    "question_type": question_type or "",
                    "knowledge_modules": ",".join(knowledge_modules),
                }
            if not show_preview and cur_dtype != "add_note":
                with st.expander("添加备注到草稿", expanded=False):
                    ncl, ncr = st.columns([2, 1])
                    with ncr:
                        selected_type_id = compact_note_type_selector()
                    with ncl:
                        with st.container(border=True):
                            with st.form("ra_add_note_form_%s" % d["draft_id"], clear_on_submit=True):
                                note_content = st.text_area("内容", placeholder="输入备注内容...", height=80,
                                                            label_visibility="collapsed")
                                cc1, cc2 = st.columns([1, 1])
                                with cc1:
                                    submitted = st.form_submit_button("添加备注", type="primary", use_container_width=True)
                                with cc2:
                                    if not selected_type_id:
                                        st.error("未选择")
                                    else:
                                        st.success(get_note_type(selected_type_id)["type_name"])
                                if submitted:
                                    if not selected_type_id:
                                        st.error("请先选择备注类型")
                                    elif not note_content.strip():
                                        st.warning("请输入备注内容")
                                    else:
                                        nt = get_note_type(selected_type_id)
                                        notes = list(snapshot.get("notes", []))
                                        notes.append({
                                            "type_id": selected_type_id,
                                            "type_name": nt["type_name"],
                                            "content": note_content,
                                        })
                                        draft_store.update_snapshot(d["draft_id"], {"notes": notes})
                                        st.success("已添加备注到草稿")
                                        _save_and_rerun()
                    notes = snapshot.get("notes", [])
                    if notes:
                        st.caption("已携带备注 %d 条" % len(notes))
                        for i, n in enumerate(notes):
                            nc1, nc2 = st.columns([4, 1])
                            nc1.write("%s | %s" % (n.get("type_name", ""), (n.get("content", "") or "")[:50]))
                            with nc2:
                                if st.button("删除", key="ra_del_note_%s_%d" % (d["draft_id"], i)):
                                    notes2 = list(snapshot.get("notes", []))
                                    notes2.pop(i)
                                    draft_store.update_snapshot(d["draft_id"], {"notes": notes2})
                                    _save_and_rerun()
            ec1, ec2 = st.columns(2)
            with ec1:
                if st.button("保存并提交", key="ra_commit", type="primary"):
                    # 提交前先保存当前编辑内容，保证提交的是最新版本
                    draft_store.update_snapshot(d["draft_id"], snap_update)
                    d2 = draft_store.get(d["draft_id"])
                    ok, msg = _commit_draft(d2, draft_store, undo_stack, user_id, sid)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
                    _save_and_rerun()
            with ec2:
                if st.button("丢弃", key="ra_discard"):
                    draft_store.discard(d["draft_id"])
                    record_log(operator="user:%s" % user_id, case_id=d.get("target_question_id"),
                               action="draft_discard", detail={"draft_id": d["draft_id"]}, session_id=sid)
                    _save_and_rerun()
        else:
            st.info("请在上方选择草稿编号查看预览" if show_preview else "请在上方选择草稿编号进行编辑修改")

        # ===== 评分细则匹配草稿（作为草稿显示在草稿区）=====
        left_matches = [
            m for m in match_store.list_all()
            if m["status"] not in ("committed", "discarded")
        ]
        if left_matches:
            st.markdown("---")
            st.caption("评分细则匹配草稿（%d 条）" % len(left_matches))
            for m in left_matches:
                status = m["status"]
                with st.container(border=True):
                    st.write("**%s** | 题号 %s" % (
                        m["match_id"], m.get("rubric_question_no") or "?",
                    ))
                    st.caption("匹配题目：%s | 置信度 %.2f | %s" % (
                        m.get("matched_question_id") or "无", m["confidence"], status,
                    ))
                    if status == "similar":
                        st.caption("已有同类备注相似度 %.2f | 处理：%s" % (
                            m.get("similarity") or 0.0, m.get("revise_action") or "未选择",
                        ))
                    with st.expander("查看并处理 %s" % m["match_id"], expanded=False):
                        st.markdown("**本次细则**")
                        st.markdown(m.get("rubric_content") or "")
                        if status == "similar":
                            st.markdown("**已有备注**")
                            st.markdown(m.get("existing_content") or "")
                            sb1, sb2, sb3 = st.columns(3)
                            if sb1.button("覆盖", key="left_overwrite_%s" % m["match_id"]):
                                match_store.update_status(m["match_id"], "similar", revise_action="overwrite")
                                record_log(operator="user:%s" % user_id,
                                           case_id=m.get("matched_question_id"),
                                           action="rubric_match_resolve",
                                           detail={"match_id": m["match_id"], "action": "overwrite",
                                                   "existing_note_id": m.get("existing_note_id")},
                                           session_id=sid)
                                _save_and_rerun()
                            if sb2.button("追加", key="left_append_%s" % m["match_id"]):
                                match_store.update_status(m["match_id"], "similar", revise_action="append")
                                record_log(operator="user:%s" % user_id,
                                           case_id=m.get("matched_question_id"),
                                           action="rubric_match_resolve",
                                           detail={"match_id": m["match_id"], "action": "append"},
                                           session_id=sid)
                                _save_and_rerun()
                            if sb3.button("跳过", key="left_skip_%s" % m["match_id"]):
                                match_store.update_status(m["match_id"], "skipped", revise_action="skip")
                                record_log(operator="user:%s" % user_id,
                                           case_id=m.get("matched_question_id"),
                                           action="rubric_match_resolve",
                                           detail={"match_id": m["match_id"], "action": "skip"},
                                           session_id=sid)
                                _save_and_rerun()
                        if status in ("low_confidence", "manual_match"):
                            new_qid = st.number_input(
                                "指定题目ID", value=0, key="left_fix_qid_%s" % m["match_id"],
                            )
                            if st.button("修正匹配", key="left_fix_%s" % m["match_id"]):
                                match_store.update_match(
                                    m["match_id"],
                                    matched_question_id=int(new_qid) if new_qid else None,
                                    status="manual_match" if new_qid else "pending",
                                )
                                record_log(operator="user:%s" % user_id,
                                           case_id=m.get("matched_question_id"),
                                           action="rubric_match_revise",
                                           detail={"match_id": m["match_id"], "new_qid": new_qid},
                                           session_id=sid)
                                _save_and_rerun()
                        if st.button("丢弃", key="left_discard_%s" % m["match_id"]):
                            match_store.update_status(m["match_id"], "discarded")
                            record_log(operator="user:%s" % user_id,
                                       case_id=m.get("matched_question_id"),
                                       action="rubric_match_resolve",
                                       detail={"match_id": m["match_id"], "action": "discard"},
                                       session_id=sid)
                            _save_and_rerun()
            mb1, mb2 = st.columns(2)
            with mb1:
                if st.button("确认批量提交匹配", type="primary", key="left_commit_matches"):
                    ok_count, fail_count, skip_count = _commit_match_drafts(match_store, user_id, sid)
                    st.success("成功 %d 条，失败 %d 条，跳过 %d 条" % (ok_count, fail_count, skip_count))
                    _save_and_rerun()
            with mb2:
                if st.button("丢弃所有匹配草稿", key="left_discard_matches"):
                    discarded = 0
                    for item in left_matches:
                        if item["status"] not in ("committed", "discarded"):
                            match_store.update_status(item["match_id"], "discarded")
                            discarded += 1
                    record_log(operator="user:%s" % user_id, case_id=None,
                               action="rubric_match_resolve",
                               detail={"action": "discard_all", "count": discarded},
                               session_id=sid)
                    _save_and_rerun()

    # --- 右侧：助手对话历史 ---
    with col_chat:
        cc1, cc2 = st.columns([4, 1])
        cc1.subheader("助手对话")
        with cc2:
            if st.button("清空对话", type="secondary", key="ra_clear_chat"):
                st.session_state["ra_history"] = []
                _save_and_rerun()
        chat_height = 1000 if draft_idx else 600
        chat_container = st.container(height=chat_height)
        with chat_container:
            for m in st.session_state["ra_history"]:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

    st.divider()

    # ===== 操作记录（预览下边，简洁摘要 + 完整细节 expander）=====
    with st.expander("操作记录", expanded=False):
        _render_operation_logs(sid)

    # ===== 撤销栈（操作记录下边）=====
    with st.expander("撤销栈", expanded=False):
        undo_items = undo_stack.list_all()
        if undo_items:
            for i, op in enumerate(reversed(undo_items)):
                st.write("%d. %s | 目标:%s | %s" % (i + 1, op["op_type"], op["target_id"], op["created_at"][:19]))
            if st.button("撤销最近一次", type="secondary"):
                op = undo_stack.pop()
                if op:
                    ok, msg = _undo_op(op, user_id, sid)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
                    _save_and_rerun()
        else:
            st.info("撤销栈为空")

    # ===== chat_input（Streamlit 限制：必须在页面最底部，不能在列/容器/expander 内）=====
    user_input = st.chat_input("输入录题指令，如：把上传的图片录成单选题...")
    if user_input:
        if perm_switches.get_emergency_stop():
            st.error("已紧急停止：请先点击“恢复运行”再发送指令。")
            st.stop()
        st.session_state["ra_history"].append({"role": "user", "content": user_input})
        api_key = get_api_key()
        if not api_key:
            st.error("DeepSeek API Key 未配置")
            st.stop()
        # 当前批次：只把所选页范围的页图传给 Agent，避免整本 PDF 塞进上下文
        active_batch = st.session_state.get("ra_active_batch")
        batch_pages = _batch_pages(active_batch) if active_batch else []
        batch_prefix = ""
        batch_image_ids = []
        if active_batch and batch_pages:
            batch_prefix = "[当前批次] %s 第 %s 页，请只处理该范围。\n" % (
                active_batch["filename"], _format_page_ranges(batch_pages),
            )
            batch_image_ids = pdf_library.get_active_page_file_ids(active_batch["file_id"])
            if not batch_image_ids:
                # 兼容旧会话：按页范围取已上传页图
                batch_image_ids = pdf_library.get_page_file_ids_in_range(
                    active_batch["file_id"], min(batch_pages), max(batch_pages),
                )
        # 本次对话实际使用的图片/PDF 刷新最后使用时间（空闲 24 小时过期）
        gallery_images = image_gallery.list_all()
        for image in gallery_images:
            image_gallery.touch(image["file_id"])
        if active_batch:
            pdf_library.touch(active_batch["file_id"])
        # 把当前会话真实 PDF 标识提供给 LLM，避免编造 local-pdf-1 之类的占位值
        pdf_prefix = ""
        pdf_refs = pdf_library.list_all()
        if pdf_refs:
            pdf_lines = []
            for pf in pdf_refs:
                line = "- %s | file_id=%s | 共 %d 页" % (
                    pf["filename"], pf["file_id"], pf["page_count"],
                )
                processed = pf.get("processed_pages", [])
                if processed:
                    line += " | 已处理 %s" % _format_page_ranges(processed)
                if pf.get("expired"):
                    line += " | 页图已过期，需重新加载批次"
                pdf_lines.append(line)
            pdf_prefix = "[会话PDF]\n" + "\n".join(pdf_lines) + "\n"
        with st.spinner("录题助手思考中..."):
            answer, steps, draft_previews = run_record_agent(
                history=st.session_state["ra_history"][:-1],
                user_input=pdf_prefix + batch_prefix + user_input,
                api_key=api_key,
                user_role=user_role,
                user_id=user_id,
                session_id=sid,
                draft_store=draft_store,
                undo_stack=undo_stack,
                image_gallery=image_gallery,
                pdf_library=pdf_library,
                fragment_store=fragment_store,
                match_store=match_store,
                pdf_local_paths=st.session_state["ra_pdf_local_paths"],
                image_file_ids=[im["file_id"] for im in gallery_images] + batch_image_ids,
                perm_switches=perm_switches,
            )
        # 本次批次已交给 Agent 处理，记录已处理页并清空当前批次
        if active_batch and batch_pages:
            pdf_library.mark_processed(active_batch["file_id"], batch_pages)
            pdf_library.set_active_pages(active_batch["file_id"], [])
            st.session_state.pop("ra_active_batch", None)
        st.session_state["ra_history"].append({"role": "assistant", "content": answer})
        if steps:
            with st.expander("工具调用步骤", expanded=False):
                shown_steps = steps[-50:] if len(steps) > 50 else steps
                if len(steps) > 50:
                    st.caption("仅显示最近 50 条工具调用，共 %d 条" % len(steps))
                for s in shown_steps:
                    if "error" in s:
                        st.error(s["error"])
                    else:
                        st.write("**%s**" % s.get("tool", "?"))
                        st.code(str(s.get("args", {})), language="json")
                        st.text(s.get("result", "")[:500])
        _save_and_rerun()

    # 兜底保存：普通交互（未触发 rerun）在此落盘
    _persist()


# ===== 确认提交三段式 =====
def _commit_draft(d, draft_store, undo_stack, user_id, sid):
    """草稿→确认→服务层三段式提交。开事务→写库→日志→撤销栈→提交。"""
    dtype = d["draft_type"]
    snap = d.get("snapshot_after", {})
    target = d.get("target_question_id")
    try:
        if dtype == "create_question":
            qid = create_question(
                content=snap.get("content", ""), answer=snap.get("answer", ""),
                analysis=snap.get("analysis", ""), source=snap.get("source", ""),
                analysis_source=snap.get("analysis_source", ""), year=snap.get("year", ""),
                paper_type=snap.get("paper_type", ""), question_no=snap.get("question_no", ""),
                question_type=snap.get("question_type", ""), knowledge_modules=snap.get("knowledge_modules", ""),
            )
            undo_stack.push("create_question", qid, None, snap)
            record_log(operator="user:%s" % user_id, case_id=qid, action="commit",
                       detail={"draft_id": d["draft_id"], "qid": qid}, session_id=sid)
            dup_msg = ""
            qno = snap.get("question_no", "")
            ptype = snap.get("paper_type", "")
            if qno:
                dups = get_question_by_no_and_paper(qno, ptype or None)
                dups_other = [x for x in dups if x["questionID"] != qid]
                if dups_other:
                    dup_msg = "；注意：题号%s已存在题目%s" % (
                        qno, ",".join(str(x["questionID"]) for x in dups_other))
            note_count = 0
            for n in snap.get("notes", []):
                try:
                    note_content = n.get("content", "")
                    if n.get("type_name") == "评分细则":
                        note_content = normalize_rubric_content(note_content)
                    create_question_note(qid, n.get("type_id"), note_content, user_id)
                    note_count += 1
                except Exception:
                    pass
            draft_store.commit(d["draft_id"])
            return True, "已提交，新题目ID: %s%s；备注%d条" % (qid, dup_msg, note_count)
        elif dtype == "update_question":
            update_question(
                target,
                content=snap.get("content", ""), answer=snap.get("answer", ""),
                analysis=snap.get("analysis", ""), source=snap.get("source", ""),
                analysis_source=snap.get("analysis_source", ""), year=snap.get("year", ""),
                paper_type=snap.get("paper_type", ""), question_no=snap.get("question_no", ""),
                question_type=snap.get("question_type", ""), knowledge_modules=snap.get("knowledge_modules", ""),
            )
            undo_stack.push("update_question", target, d.get("snapshot_before"), snap)
            record_log(operator="user:%s" % user_id, case_id=target, action="commit",
                       detail={"draft_id": d["draft_id"]}, session_id=sid)
            note_count = 0
            for n in snap.get("notes", []):
                try:
                    note_content = n.get("content", "")
                    if n.get("type_name") == "评分细则":
                        note_content = normalize_rubric_content(note_content)
                    create_question_note(target, n.get("type_id"), note_content, user_id)
                    note_count += 1
                except Exception:
                    pass
            draft_store.commit(d["draft_id"])
            return True, "已提交修改，题目ID: %s；备注%d条" % (target, note_count)
        elif dtype == "add_note":
            note_content = snap.get("content", "")
            if snap.get("type_name") == "评分细则":
                note_content = normalize_rubric_content(note_content)
            note_id = create_question_note(
                snap.get("target_question_id"), snap.get("type_id"),
                note_content, user_id,
            )
            undo_stack.push("add_note", note_id, None, snap)
            record_log(operator="user:%s" % user_id, case_id=snap.get("target_question_id"),
                       action="commit", detail={"draft_id": d["draft_id"], "note_id": note_id}, session_id=sid)
            draft_store.commit(d["draft_id"])
            return True, "已提交备注，备注ID: %s" % note_id
        else:
            return False, "未知草稿类型: %s" % dtype
    except Exception as e:
        return False, "提交失败: %s" % e


def _commit_match_drafts(match_store, user_id, sid):
    """批量提交匹配草稿，逐条调 create_question_note，单条失败不阻塞其余。

    similar 状态（已有基本一致的同类备注）按用户选择处理：
      - overwrite：先软删除已有同类型备注，再新建
      - append：直接新建（同类备注允许共存）
      - 未选择 / skip：跳过
    """
    ok_count = 0
    fail_count = 0
    skip_count = 0
    for m in match_store.list_all():
        if m["status"] in ("skipped", "committed", "discarded"):
            continue
        if not m.get("matched_question_id") or not m.get("note_type_id"):
            continue
        action = m.get("revise_action")
        if m["status"] == "similar" and action not in ("overwrite", "append"):
            skip_count += 1
            continue
        try:
            if m["status"] == "similar" and action == "overwrite" and m.get("existing_note_id"):
                soft_delete_question_note(m["existing_note_id"], user_id)
            note_content = normalize_rubric_content(m.get("rubric_content", ""))
            note_id = create_question_note(
                m["matched_question_id"], m["note_type_id"], note_content, user_id,
            )
            if not note_id:
                fail_count += 1
                continue
            match_store.update_status(m["match_id"], "committed")
            record_log(
                operator="user:%s" % user_id, case_id=m["matched_question_id"],
                action="rubric_upload",
                detail={"match_id": m["match_id"], "note_id": note_id,
                        "resolve_action": action},
                session_id=sid,
            )
            ok_count += 1
        except Exception:
            fail_count += 1
    return ok_count, fail_count, skip_count


def _undo_op(op, user_id, sid):
    """撤销操作：按 op_type 还原。"""
    try:
        if op["op_type"] == "create_question":
            move_to_recycle_bin(op["target_id"])
            record_log(operator="user:%s" % user_id, case_id=op["target_id"], action="undo",
                       detail={"op_type": op["op_type"]}, session_id=sid)
            return True, "已撤销创建，题目 %s 移入回收站" % op["target_id"]
        elif op["op_type"] == "update_question":
            before = op.get("snapshot_before", {})
            if before:
                update_question(
                    op["target_id"],
                    content=before.get("content", ""), answer=before.get("answer", ""),
                    analysis=before.get("analysis", ""), source=before.get("source", ""),
                    analysis_source=before.get("analysis_source", ""), year=before.get("year", ""),
                    paper_type=before.get("paper_type", ""), question_no=before.get("question_no", ""),
                    question_type=before.get("question_type", ""), knowledge_modules=before.get("knowledge_modules", ""),
                )
                record_log(operator="user:%s" % user_id, case_id=op["target_id"], action="undo",
                           detail={"op_type": op["op_type"]}, session_id=sid)
                return True, "已撤销修改，题目 %s 已还原" % op["target_id"]
            return False, "无修改前快照"
        elif op["op_type"] == "add_note":
            soft_delete_question_note(op["target_id"], user_id)
            record_log(operator="user:%s" % user_id, case_id=op["target_id"], action="undo",
                       detail={"op_type": op["op_type"]}, session_id=sid)
            return True, "已撤销备注，备注 %s 已软删除" % op["target_id"]
        else:
            return False, "不可撤销的操作: %s" % op["op_type"]
    except Exception as e:
        return False, "撤销失败: %s" % e
