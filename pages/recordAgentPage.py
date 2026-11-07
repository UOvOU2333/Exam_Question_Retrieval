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
  顶部：上传文件（expander）
  标题行：录题助手（左）| 草稿编号 number_input（右）——同 updatePage 题号位置
  双栏：左侧手动修改区 | 右侧助手对话历史
  预览：双栏之下，用 render_markdown 渲染选中草稿（参考上传/更新页调用）
  操作记录：预览之下，简洁摘要 + 完整细节 expander
  撤销栈：操作记录之下
  匹配确认：有匹配草稿时显示
  chat_input：页面最底部（Streamlit 硬性限制）
"""
import streamlit as st
import os
import uuid
import json

from utils.auth_utils import require_permission
from utils.permissions import has_permission, is_admin
from services.record_agent_auth_services import is_record_agent_enabled
from services.log_services import record_log, get_session_logs
from services.question_services import (
    create_question,
    update_question,
    move_to_recycle_bin,
    get_question_by_id,
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
)
from utils.render_utils import render_markdown
from utils.multi_func import rich_markdown
from utils.note_utils import display_notes_list, compact_note_type_selector
from tools.exam_type_utils import QUESTION_TYPES, KNOWLEDGE_MODULES

IMAGE_DIR = "static/images/questions"
os.makedirs(IMAGE_DIR, exist_ok=True)


_ACTION_LABELS = {
    "tool_call": "工具调用",
    "draft_create": "创建草稿",
    "draft_discard": "丢弃草稿",
    "pdf_upload": "上传PDF",
    "image_upload": "上传图片",
    "commit": "提交",
    "undo": "撤销",
    "rubric_upload": "上传细则",
    "rubric_match_revise": "修正匹配",
    "permission_denied": "拒绝访问",
}


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


def _render_note_section(d, draft_store, user_id, sid):
    """备注栏目：复用 question_notes_component 表层布局，底层适配草稿流程。

    - update_question 草稿：展示 target_question_id 已有备注 + 添加备注草稿入口
    - create_question 草稿：新题未提交，显示"暂无备注"
    """
    cur_dtype = d["draft_type"]
    target_qid = d.get("target_question_id")

    st.subheader("题目备注")

    if cur_dtype == "create_question" or not target_qid:
        st.info("暂无备注")
        return

    display_notes_list(target_qid)

    col_left, col_right = st.columns([2, 1])
    with col_right:
        selected_type_id = compact_note_type_selector()
    with col_left:
        with st.container(border=True):
            with st.form("ra_add_note_form", clear_on_submit=True):
                note_content = st.text_area(
                    "内容", placeholder="输入备注内容...", height=80,
                    label_visibility="collapsed",
                )
                c1, c2 = st.columns([1, 1])
                with c1:
                    submitted = st.form_submit_button("新增备注草稿", type="primary", use_container_width=True)
                with c2:
                    if not selected_type_id:
                        st.error("未选择")
                    else:
                        st.success(get_note_type(selected_type_id)["type_name"])
                if submitted:
                    if not selected_type_id:
                        st.error("请先选择一个备注类型")
                    elif not note_content.strip():
                        st.warning("请输入备注内容")
                    else:
                        nt = get_note_type(selected_type_id)
                        snap = {
                            "target_question_id": target_qid,
                            "type_id": selected_type_id,
                            "type_name": nt["type_name"],
                            "content": note_content,
                        }
                        did = draft_store.add("add_note", snap, target_question_id=target_qid)
                        if did:
                            record_log(operator="user:%s" % user_id, case_id=target_qid,
                                       action="draft_create", detail={"draft_id": did, "draft_type": "add_note"},
                                       session_id=sid)
                            st.success("已创建备注草稿 %s" % did)
                            st.rerun()
                        else:
                            st.error("草稿数已达上限")


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

    # ===== 顶部：上传文件 =====
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
                        ok, msg = validate_pdf(f.name, fbytes)
                        if not ok:
                            st.error("%s: %s" % (f.name, msg))
                            continue
                        try:
                            local_file_id, local_path = save_pdf_to_local(fbytes, f.name)
                            st.session_state["ra_pdf_local_paths"][local_file_id] = local_path
                            page_file_ids = upload_pdf_pages_as_images(
                                local_path, f.name, api_key=api_key
                            )
                            remove_local_pdf(local_file_id, st.session_state["ra_pdf_local_paths"])
                            pdf_library.add(
                                local_file_id, f.name, len(fbytes),
                                len(page_file_ids), "multi_question",
                                page_file_ids=page_file_ids,
                            )
                            record_log(
                                operator="user:%s" % user_id, case_id=None,
                                action="pdf_upload",
                                detail={"file_id": local_file_id, "filename": f.name,
                                        "pages": len(page_file_ids)},
                                session_id=sid,
                            )
                            st.success("已上传 PDF: %s（%d 页图片）" % (f.name, len(page_file_ids)))
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
                        st.rerun()
        if pdfs:
            st.write("**PDF**")
            for pf in pdfs:
                pc1, pc2 = st.columns([4, 1])
                pc1.write("%s | %s | %d bytes | %d 页" % (pf["filename"], pf["file_id"], pf["bytes_size"], pf["page_count"]))
                with pc2:
                    if st.button("删除", key="del_pdf_%s" % pf["file_id"]):
                        page_fids = pdf_library.remove(pf["file_id"])
                        if page_fids:
                            delete_page_images(page_fids, api_key=get_api_key())
                        remove_local_pdf(pf["file_id"], st.session_state["ra_pdf_local_paths"])
                        st.rerun()

    # ===== 标题行 + 草稿编号（仿 updatePage：标题左 | 编号右）=====
    pending_drafts = draft_store.list_pending()
    col_title, col_draft = st.columns(2)
    with col_title:
        st.title("录题助手")
        st.caption("当前用户：%s | 会话：%s" % (username, sid))
    with col_draft:
        if pending_drafts:
            draft_idx = st.number_input(
                "草稿编号（0=不选，1~%d 选择对应草稿）" % len(pending_drafts),
                min_value=0, max_value=len(pending_drafts), value=0, step=1,
                key="ra_draft_sel",
            )
        else:
            st.info("暂无草稿，上传文件后与助手对话生成草稿")
            draft_idx = 0

    # ===== 双栏：左侧手动修改区 | 右侧助手对话 =====
    edit_content = edit_answer = edit_analysis = None
    cur_dtype = None
    cur_draft = None
    col_edit, col_chat = st.columns(2)

    # --- 左侧：手动修改区 ---
    with col_edit:
        st.subheader("手动修改区")
        if pending_drafts and int(draft_idx) > 0:
            d = pending_drafts[int(draft_idx) - 1]
            snapshot = d.get("snapshot_after", {})
            cur_dtype = d["draft_type"]
            cur_draft = d
            st.caption("%s [%s]" % (d["draft_id"], cur_dtype))
            rich_markdown(IMAGE_DIR, True, None)
            snap_update = {}
            if cur_dtype == "add_note":
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
            if st.button("保存修改到草稿", key="ra_save_draft", type="secondary"):
                draft_store.update_snapshot(d["draft_id"], snap_update)
                st.success("已保存修改到草稿")
                st.rerun()
            ec1, ec2 = st.columns(2)
            with ec1:
                if st.button("确认提交", key="ra_commit", type="primary"):
                    draft_store.update_snapshot(d["draft_id"], snap_update)
                    d2 = draft_store.get(d["draft_id"])
                    ok, msg = _commit_draft(d2, draft_store, undo_stack, user_id, sid)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
                    st.rerun()
            with ec2:
                if st.button("丢弃", key="ra_discard"):
                    draft_store.discard(d["draft_id"])
                    record_log(operator="user:%s" % user_id, case_id=d.get("target_question_id"),
                               action="draft_discard", detail={"draft_id": d["draft_id"]}, session_id=sid)
                    st.rerun()
        else:
            st.info("请在上方选择草稿编号进行编辑修改")

    # --- 右侧：助手对话历史 ---
    with col_chat:
        cc1, cc2 = st.columns([4, 1])
        cc1.subheader("助手对话")
        with cc2:
            if st.button("清空对话", type="secondary", key="ra_clear_chat"):
                st.session_state["ra_history"] = []
                st.rerun()
        chat_container = st.container(height=900)
        with chat_container:
            for m in st.session_state["ra_history"]:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

    st.divider()

    # ===== 预览（对话下边，用 render_markdown 渲染，参考上传/更新页）=====
    if edit_content is not None:
        st.subheader("预览")
        if cur_dtype == "add_note":
            st.markdown("### 备注内容")
            if edit_content.strip():
                render_markdown(edit_content)
            else:
                st.info("开始输入后，这里会实时预览备注内容")
        else:
            has_any = False
            if edit_content.strip():
                st.markdown("### 题目内容")
                render_markdown(edit_content)
                has_any = True
            if edit_answer.strip():
                st.markdown("### 答案")
                render_markdown(edit_answer)
                has_any = True
            if edit_analysis.strip():
                st.markdown("### 解析")
                render_markdown(edit_analysis)
                has_any = True
            if not has_any:
                st.info("开始输入后，这里会实时预览 Markdown 内容")
            if cur_draft is not None:
                _render_note_section(cur_draft, draft_store, user_id, sid)

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
                    st.rerun()
        else:
            st.info("撤销栈为空")

    # ===== 匹配确认（有匹配草稿时显示）=====
    pending_matches = match_store.list_all()
    if pending_matches:
        with st.expander("评分细则匹配结果（%d 条）" % len(pending_matches), expanded=False):
            st.caption("确认后批量提交到对应题目的备注。低置信度高亮，已有细则跳过。")
            for m in pending_matches:
                status = m["status"]
                row_color = {"skipped": "gray", "low_confidence": "orange", "manual_match": "red"}.get(status, "green")
                with st.container():
                    mc1, mc2, mc3, mc4 = st.columns([2, 2, 2, 2])
                    mc1.write("**%s** 题号:%s" % (m["match_id"], m.get("rubric_question_no") or "?"))
                    mc2.write("匹配题目:%s" % (m.get("matched_question_id") or "无"))
                    mc3.write("置信度:%.2f" % m["confidence"])
                    mc4.markdown(":%s[%s]" % (row_color, status))
                    if status in ("low_confidence", "manual_match"):
                        with st.expander("人工修正 %s" % m["match_id"], expanded=False):
                            new_qid = st.number_input("指定题目ID", value=0, key="fix_qid_%s" % m["match_id"])
                            if st.button("修正匹配", key="fix_%s" % m["match_id"]):
                                match_store.update_match(m["match_id"], matched_question_id=int(new_qid) if new_qid else None,
                                                         status="manual_match" if new_qid else "pending")
                                record_log(operator="user:%s" % user_id, case_id=m.get("matched_question_id"),
                                           action="rubric_match_revise",
                                           detail={"match_id": m["match_id"], "new_qid": new_qid}, session_id=sid)
                                st.rerun()
            if st.button("确认批量提交", type="primary"):
                ok_count, fail_count = _commit_match_drafts(match_store, user_id, sid)
                st.success("成功 %d 条，失败 %d 条" % (ok_count, fail_count))
                st.rerun()

    # ===== chat_input（Streamlit 限制：必须在页面最底部，不能在列/容器/expander 内）=====
    user_input = st.chat_input("输入录题指令，如：把上传的图片录成单选题...")
    if user_input:
        st.session_state["ra_history"].append({"role": "user", "content": user_input})
        api_key = get_api_key()
        if not api_key:
            st.error("DeepSeek API Key 未配置")
            st.stop()
        with st.spinner("录题助手思考中..."):
            answer, steps, draft_previews = run_record_agent(
                history=st.session_state["ra_history"][:-1],
                user_input=user_input,
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
                image_file_ids=[im["file_id"] for im in image_gallery.list_all()]
                              + pdf_library.all_page_file_ids(),
            )
        st.session_state["ra_history"].append({"role": "assistant", "content": answer})
        if steps:
            with st.expander("工具调用步骤", expanded=False):
                for s in steps:
                    if "error" in s:
                        st.error(s["error"])
                    else:
                        st.write("**%s**" % s.get("tool", "?"))
                        st.code(str(s.get("args", {})), language="json")
                        st.text(s.get("result", "")[:500])
        st.rerun()


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
            draft_store.commit(d["draft_id"])
            return True, "已提交，新题目ID: %s" % qid
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
            draft_store.commit(d["draft_id"])
            return True, "已提交修改，题目ID: %s" % target
        elif dtype == "add_note":
            note_id = create_question_note(
                snap.get("target_question_id"), snap.get("type_id"),
                snap.get("content", ""), user_id,
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
    """批量提交匹配草稿，逐条调 create_question_note，单条失败不阻塞其余。"""
    ok_count = 0
    fail_count = 0
    for m in match_store.list_all():
        if m["status"] in ("skipped", "committed", "discarded"):
            continue
        if not m.get("matched_question_id") or not m.get("note_type_id"):
            continue
        try:
            note_id = create_question_note(
                m["matched_question_id"], m["note_type_id"], m["rubric_content"], user_id,
            )
            match_store.update_status(m["match_id"], "committed")
            record_log(operator="user:%s" % user_id, case_id=m["matched_question_id"],
                       action="rubric_upload", detail={"match_id": m["match_id"], "note_id": note_id}, session_id=sid)
            ok_count += 1
        except Exception as e:
            fail_count += 1
    return ok_count, fail_count


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
