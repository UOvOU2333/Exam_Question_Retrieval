import os
import streamlit as st

from utils.auth_utils import require_role
from utils.render_utils import render_markdown
from utils.rich_text import rich_markdown
from services.question_services import create_question

# =========================
# 图片存储配置
# =========================
IMAGE_DIR = "static/images/questions"
os.makedirs(IMAGE_DIR, exist_ok=True)

def upload():
    # ===== 权限校验 =====
    require_role("admin", "editor")

    st.title("试题上传")

    st.divider()

    # =========================
    # Markdown 编辑 + 实时预览
    # =========================
    col_edit, col_preview = st.columns(2)

    with col_edit:

        rich_markdown(IMAGE_DIR)

        st.divider()

        content = st.text_area(
            "试题内容",
            height=220,
            placeholder="请输入题目正文（支持 Markdown / LaTeX / 图片）"
        )

        answer = st.text_area(
            "答案",
            height=120,
            placeholder="请输入答案（支持 Markdown / LaTeX）"
        )

        analysis = st.text_area(
            "解析",
            height=180,
            placeholder="请输入解析（支持 Markdown / LaTeX）"
        )

        source = st.text_input("题目来源")
        analysis_source = st.text_input("解析来源")

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

        create_question(
            content=content,
            answer=answer,
            analysis=analysis,
            source=source,
            analysis_source=analysis_source
        )

        st.success("🎉 试题上传成功")
        st.session_state["nav"] = "数据库"
        st.rerun()
