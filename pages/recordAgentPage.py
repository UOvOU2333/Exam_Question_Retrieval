# pages/recordAgentPage.py
"""录题 Agent 主页面。

三层权限校验（页面层）：
  1. require_permission('record_agent')
  2. is_record_agent_enabled(user_id)
  3. has_permission(role, 'upload')
任一未通过写 permission_denied 日志并拒绝。

安全核心——确认提交三段式：
  草稿（session_state）→ 用户确认 → 服务层写库（事务 + 撤销栈 + 日志）
  工具执行层禁直写，仅生成草稿。
"""
import streamlit as st
import os
import uuid

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
from services.note_services import create_question_note, soft_delete_question_note
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


def record_agent_page():
    """录题 Agent 主页面入口。"""
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
            detail={"layer": "page", "reason": "未授权录题 Agent"},
        )
        st.error("您未授权使用录题 Agent，请联系管理员授权。")
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
    # 页面加载时清理本地缓存中超过 1 小时的旧文件，避免缓存堆积
    cleanup_local_cache()
    if "ra_session_id" not in st.session_state:
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

    st.title("录题 Agent")
    st.caption("当前用户：%s | 会话：%s" % (username, sid))

    # ===== 顶部：清空对话 =====
    col_t1, col_t2 = st.columns([6, 1])
    with col_t2:
        if st.button("清空对话", type="secondary"):
            st.session_state["ra_history"] = []
            st.rerun()

    # ===== 上传区（图片 + PDF 并列）=====
    st.subheader("上传文件")
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
        st.caption("PDF 上传（≤200MiB，每页转图片上传由 AI 视觉识别）")
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
                        # PDF 每页渲染为 PNG 上传 Files API，LLM 视觉理解
                        local_file_id, local_path = save_pdf_to_local(fbytes, f.name)
                        st.session_state["ra_pdf_local_paths"][local_file_id] = local_path
                        page_file_ids = upload_pdf_pages_as_images(
                            local_path, f.name, api_key=api_key
                        )
                        # 渲染上传完成，删除本地临时 PDF
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

    # ===== 会话文件区（expander）=====
    with st.expander("本次会话文件", expanded=False):
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
                pc1.write("%s | %s | %d bytes" % (pf["filename"], pf["file_id"], pf["bytes_size"]))
                with pc2:
                    if st.button("删除", key="del_pdf_%s" % pf["file_id"]):
                        # 先删 Files API 上的页面图片，再清本地
                        page_fids = pdf_library.remove(pf["file_id"])
                        if page_fids:
                            delete_page_images(page_fids, api_key=get_api_key())
                        remove_local_pdf(pf["file_id"], st.session_state["ra_pdf_local_paths"])
                        st.rerun()
        if not images and not pdfs:
            st.info("本次会话未上传文件")

    st.divider()

    # ===== 聊天区 =====
    st.subheader("对话")
    chat_container = st.container(height=400)
    with chat_container:
        for m in st.session_state["ra_history"]:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    user_input = st.chat_input("输入录题指令，如：把上传的图片录成单选题...")
    if user_input:
        st.session_state["ra_history"].append({"role": "user", "content": user_input})
        api_key = get_api_key()
        if not api_key:
            st.error("DeepSeek API Key 未配置")
            st.stop()
        with st.spinner("录题 Agent 思考中..."):
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

    # ===== 草稿列表区 =====
    pending_drafts = draft_store.list_pending()
    if pending_drafts:
        st.divider()
        st.subheader("草稿列表（待确认）")
        for d in pending_drafts:
            with st.expander("%s [%s] %s" % (d["draft_id"], d["draft_type"], d["status"]), expanded=False):
                snapshot = d.get("snapshot_after", {})
                editing = st.session_state.get("ra_editing_draft") == d["draft_id"]
                if editing:
                    # 编辑表单：可修改题目正文/答案/解析后保存
                    edit_content = st.text_area(
                        "题目正文", value=snapshot.get("content", ""), height=150,
                        key="edit_content_%s" % d["draft_id"])
                    edit_answer = st.text_area(
                        "答案", value=snapshot.get("answer", ""), height=80,
                        key="edit_answer_%s" % d["draft_id"])
                    edit_analysis = st.text_area(
                        "解析", value=snapshot.get("analysis", ""), height=100,
                        key="edit_analysis_%s" % d["draft_id"])
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        if st.button("保存修改", key="save_edit_%s" % d["draft_id"], type="primary"):
                            draft_store.update_snapshot(d["draft_id"], {
                                "content": edit_content, "answer": edit_answer, "analysis": edit_analysis,
                            })
                            st.session_state.pop("ra_editing_draft", None)
                            st.rerun()
                    with ec2:
                        if st.button("取消", key="cancel_edit_%s" % d["draft_id"]):
                            st.session_state.pop("ra_editing_draft", None)
                            st.rerun()
                else:
                    # MD 预览
                    content_md = snapshot.get("content", "")
                    if content_md:
                        render_markdown(content_md, header="**题目**")
                    if snapshot.get("answer"):
                        render_markdown(snapshot["answer"], header="**答案**")
                    if snapshot.get("analysis"):
                        render_markdown(snapshot["analysis"], header="**解析**")
                    # 元信息
                    meta_keys = ["year", "paper_type", "question_no", "question_type", "knowledge_modules"]
                    meta = {k: snapshot.get(k, "") for k in meta_keys if snapshot.get(k)}
                    if meta:
                        st.caption(" | ".join("%s: %s" % (k, v) for k, v in meta.items()))
                    # 确认/编辑/丢弃
                    dc1, dc2, dc3 = st.columns(3)
                    with dc1:
                        if st.button("确认提交", key="commit_%s" % d["draft_id"], type="primary"):
                            ok, msg = _commit_draft(d, draft_store, undo_stack, user_id, sid)
                            if ok:
                                st.success(msg)
                            else:
                                st.error(msg)
                            st.rerun()
                    with dc2:
                        if st.button("编辑", key="edit_%s" % d["draft_id"]):
                            st.session_state["ra_editing_draft"] = d["draft_id"]
                            st.rerun()
                    with dc3:
                        if st.button("丢弃", key="discard_%s" % d["draft_id"]):
                            draft_store.discard(d["draft_id"])
                            record_log(operator="user:%s" % user_id, case_id=d.get("target_question_id"),
                                       action="draft_discard", detail={"draft_id": d["draft_id"]}, session_id=sid)
                            st.rerun()

    # ===== 匹配确认 UI =====
    pending_matches = match_store.list_all()
    if pending_matches:
        st.divider()
        st.subheader("评分细则匹配结果")
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
                # 人工修正
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
        # 批量提交
        with st.expander("批量提交（危险操作）", expanded=False):
            st.warning("将把已匹配的评分细则写入对应题目备注，请确认。")
            if st.button("确认批量提交", type="primary"):
                ok_count, fail_count = _commit_match_drafts(match_store, user_id, sid)
                st.success("成功 %d 条，失败 %d 条" % (ok_count, fail_count))
                st.rerun()

    # ===== 底部：操作记录 + 撤销栈 =====
    st.divider()
    bc1, bc2 = st.columns(2)
    with bc1:
        with st.expander("操作记录", expanded=False):
            logs = get_session_logs(sid, limit=50)
            for log in logs:
                st.write("[%s] %s | %s | %s" % (log["created_at"][:19], log["operator"], log["action"], (log.get("detail") or "")[:80]))
            if not logs:
                st.info("暂无操作记录")
    with bc2:
        with st.expander("撤销栈（危险操作）", expanded=False):
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
