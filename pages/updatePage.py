import os
import streamlit as st

from utils.auth_utils import require_role
from utils.render_utils import render_markdown
from utils.multi_func import rich_markdown
from services.question_services import update_question, search_qid


# =========================
# 图片存储配置
# =========================
IMAGE_DIR = "static/images/questions"
os.makedirs(IMAGE_DIR, exist_ok=True)

def update():
    # ===== 权限校验 =====
    require_role("admin", "editor")
    
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

        st.divider()

    if qid != None and qInfo:
        # =========================
        # Markdown 编辑 + 实时预览
        # =========================
        col_edit, col_preview = st.columns(2)

        with col_edit:

            rich_markdown(IMAGE_DIR)

            st.divider()

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
