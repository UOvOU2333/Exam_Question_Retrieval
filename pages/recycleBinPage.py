import streamlit as st
import streamlit_antd_components as sac

from services.question_services import get_question_by_id
from services.recycleBin_services import get_questions_in_recycle_bin, restore_the_question, delete_question
from utils.auth_utils import require_role, check_role
from utils.note_utils import display_notes_list
from utils.render_utils import render_markdown


def recycle_bin():
    # ===== 权限校验 =====
    require_role("editor", "admin")

    if "show_delete_total_dialog" not in st.session_state:
        st.session_state.show_delete_total_dialog = False
        st.session_state.delete_qid = None

    if "show_restore_dialog" not in st.session_state:
        st.session_state.show_restore_dialog = False
        st.session_state.restore_qid = None

    st.title("回收站")
    st.divider()

    # ===== 获取回收站里的题目 =====
    results = get_questions_in_recycle_bin()

    # ===== 渲染题目 =====
    if not results:
        st.warning("未找到相关试题")
        return

    st.success(f"共找到 {len(results)} 条结果")

    for i in results:
        q = get_question_by_id(i)
        qid = q["questionID"]
        content = q["content"]
        answer = q["answer"]
        analysis = q["analysis"]
        source = q["source"]
        analysis_source = q["analysis_source"]
        year = q["year"]
        paper_type = q["paper_type"]
        question_no = q["question_no"]

        with st.expander(f"📘 题目 #{qid}", expanded=False):

            st.markdown("### 题目内容")
            render_markdown(content)

            if answer:
                st.markdown("### 答案")
                render_markdown(answer)

            if analysis:
                st.markdown("### 解析")
                render_markdown(analysis)

            caption_parts = []
            if year:
                caption_parts.append(f"📅 年份：{year}")
            if paper_type:
                caption_parts.append(f"📥 卷种：{paper_type}")
            if source:
                caption_parts.append(f"📌 来源：{source}")
            if question_no:
                caption_parts.append(f"📑 题号：{question_no}")
            if analysis_source:
                caption_parts.append(f"🔍 解析来源：{analysis_source}")

            if caption_parts:
                st.caption(" | ".join(caption_parts))

            display_notes_list(qid)

            if check_role("admin", "editor"):
                col1, col2, col3 = st.columns([3, 1, 1])  # 使用三列布局，左侧和右侧放按钮

                with col1:
                    if st.button("恢复试题",
                                 key=f"restore_btn_{qid}",
                                 type="primary"):
                        st.session_state.show_restore_dialog = True
                        st.session_state.restore_qid = qid
                        st.rerun()

                with col2:
                    st.empty()

                with col3:
                    if st.button("彻底删除",
                                 key=f"total_delete_btn_{qid}",
                                 type="secondary"):
                        st.session_state.show_delete_total_dialog = True
                        st.session_state.delete_qid = qid
                        st.rerun()

    # 在循环结束后显示对话框
    if st.session_state.get("show_restore_dialog", False) and st.session_state.restore_qid:
        restore_confirm_dialog(st.session_state.restore_qid)

    if st.session_state.get("show_delete_total_dialog", False) and st.session_state.delete_qid:
        delete_total_confirm_dialog(st.session_state.delete_qid)


# =========================
# 彻底删除确认对话框函数
# =========================
@st.dialog("确认彻底删除", width="small")
def delete_total_confirm_dialog(qid):
    st.warning(f"⚠️ 确定要彻底删除题目 ID {qid} 吗？（不可恢复）")

    col_confirm1, col_confirm2 = st.columns(2)

    with col_confirm1:
        if st.button("确定",
                     type="primary",
                     key=f"confirm_delete_btn_{qid}",
                     use_container_width=True):
            try:
                delete_question(qid)
                st.success(f"✅ 题目 ID {qid} 已彻底删除")
                st.session_state.show_delete_total_dialog = False
                st.rerun()
            except Exception as e:
                st.error(f"❌ 删除失败：{str(e)}")

    with col_confirm2:
        if st.button("取消",
                     type="secondary",
                     key=f"not_delete_btn_{qid}",
                     use_container_width=True):
            st.session_state.show_delete_total_dialog = False
            st.rerun()


# =========================
# 恢复试题确认对话框函数
# =========================
@st.dialog("确认恢复", width="small")
def restore_confirm_dialog(qid):
    st.warning(f"⚠️ 确定要恢复题目 ID {qid} 吗？")

    col_confirm3, col_confirm4 = st.columns(2)

    with col_confirm3:
        if st.button("确定",
                     type="primary",
                     key=f"confirm_restore_btn_{qid}",
                     use_container_width=True):
            try:
                restore_the_question(qid)
                st.success(f"✅ 题目 ID {qid} 已成功恢复")
                st.session_state.show_restore_dialog = False
                st.rerun()
            except Exception as e:
                st.error(f"❌ 删除失败：{str(e)}")

    with col_confirm4:
        if st.button("取消",
                     type="secondary",
                     key=f"not_restore_btn_{qid}",
                     use_container_width=True):
            st.session_state.show_restore_dialog = False
            st.rerun()
