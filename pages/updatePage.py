import os
import streamlit as st

from utils.auth_utils import require_role
from utils.render_utils import render_markdown
from utils.multi_func import rich_markdown
from services.question_services import update_question, search_qid, move_to_recycle_bin

# =========================
# 图片存储配置
# =========================
IMAGE_DIR = "static/images/questions"
os.makedirs(IMAGE_DIR, exist_ok=True)


def update():
    # ===== 权限校验 =====
    require_role("admin", "editor")

    if "show_delete_dialog" not in st.session_state:
        st.session_state.show_delete_dialog = False
    
    qid = st.session_state.get("update_qid")

    col_title, col_qid = st.columns(2)

    with col_title:
        st.title("试题更新")

    with col_qid:
        qid = st.number_input(value=qid,min_value=0, label="被修改题目编号")

    qInfo = search_qid(qid)

    if qid == None:
        st.error("请输入更新题目ID")
    else:
        if not qInfo:
            st.error("题目不存在")
        else:
            st.success(f"当前更新题目ID: {qid}")

            ori_content = qInfo["content"]
            ori_answer = qInfo["answer"]
            ori_analysis = qInfo["analysis"]
            ori_source = qInfo["source"]
            ori_analysis_source = qInfo["analysis_source"]
            ori_year = qInfo["year"]
            ori_paper_type = qInfo["paper_type"]
            ori_question_no = qInfo["question_no"]

    if qid != None and qInfo:
        # =========================
        # Markdown 编辑 + 实时预览
        # =========================

        rich_markdown(IMAGE_DIR, False, qid)

        col_edit, col_preview = st.columns(2)

        with col_edit:

            content = st.text_area(
                "试题内容",
                value=ori_content,
                height=220,
            )

            answer = st.text_area(
                "答案",
                height=120,
                value=ori_answer
            )

            analysis = st.text_area(
                "解析",
                height=180,
                value=ori_analysis
            )

            year = st.number_input("年份", min_value=1980, max_value=2050, step=10, value=ori_year)
            paper_type = st.text_input("卷种",
                value=ori_paper_type)
            question_no = st.text_input("题号", value=ori_question_no)

            source = st.text_input("题目来源", value=ori_source)
            analysis_source = st.text_input("解析来源", value=ori_analysis_source)

        with col_preview:
            st.subheader("👀 实时预览")

            if content.strip():
                st.markdown("### 题目内容")
                render_markdown(content)

            if answer.strip():
                st.markdown("### 答案")
                render_markdown(answer)

            if analysis.strip():
                st.markdown("### 解析")
                render_markdown(analysis)

            if not (content.strip() or answer.strip() or analysis.strip()):
                st.info("开始输入后，这里会实时预览 Markdown 内容")

        st.divider()

        role = st.session_state["role"]
        col1, col2, col3 = st.columns([3, 1, 1])  # 使用三列布局，左侧和右侧放按钮

        with col1:
            # =========================
            # 提交试题
            # =========================
            if st.button("提交试题", type="primary"):
                if not content.strip():
                    st.error("❌ 题目内容不能为空")
                    return

                update_question(
                    qid=qid,
                    content=content,
                    answer=answer,
                    analysis=analysis,
                    source=source,
                    analysis_source=analysis_source,
                    year=year,
                    paper_type=paper_type,
                    question_no=question_no
                )

                st.success("🎉 试题上传成功")

        with col2:
            # ============
            # 留空
            # ============
            st.empty()

        with col3:
            # ==================
            # 删除试题
            # ==================
            if st.button("删除试题",
                         type="secondary",
                         disabled=(role != "admin")):
                st.session_state.show_delete_dialog = True

        # =========================
        # 删除确认对话框
        # =========================
        if st.session_state.get("show_delete_dialog", False):
            delete_confirm_dialog(qid)


# =========================
# 删除确认对话框函数
# =========================
@st.dialog("确认删除", width="small")
def delete_confirm_dialog(qid):
    st.warning(f"⚠️ 确定要删除题目 ID {qid} 吗？（将移动到回收站）")

    col_confirm1, col_confirm2 = st.columns(2)

    with col_confirm1:
        if st.button("确定", type="primary", use_container_width=True):
            try:
                move_to_recycle_bin(qid)
                st.success(f"✅ 题目 ID {qid} 已成功移至回收站")
                st.session_state.show_delete_dialog = False
                st.rerun()
            except Exception as e:
                st.error(f"❌ 删除失败：{str(e)}")

    with col_confirm2:
        if st.button("取消", type="secondary", use_container_width=True):
            st.session_state.show_delete_dialog = False
            st.rerun()
