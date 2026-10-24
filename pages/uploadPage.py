import os
import re
import streamlit as st

from utils.auth_utils import require_role
from utils.render_utils import render_markdown
from utils.multi_func import rich_markdown
from services.question_services import create_question
from tools.exam_type_utils import (
    QUESTION_TYPES,
    KNOWLEDGE_MODULES,
    detect_question_type,
)

# =========================
# 图片存储配置
# =========================
IMAGE_DIR = "static/images/questions"
os.makedirs(IMAGE_DIR, exist_ok=True)

def increment_number_in_string(s):
    """将字符串中的数字部分 +1，如果没有数字则返回原字符串"""
    match = re.search(r'\d+', s)
    if match:
        num_str = match.group()
        new_num = str(int(num_str) + 1)
        return s.replace(num_str, new_num, 1)  # 只替换第一个数字
    return s

def upload():
    # ===== 权限校验 =====
    require_role("editor", "admin")

    st.title("试题上传")

    key_suffix = st.session_state.get("form_version", 0)
    if st.session_state.get(f"upload_year_{key_suffix}", 0) == 0:
        st.session_state[f"upload_year_{key_suffix}"] = 2020

    col_edit, col_preview = st.columns(2)
    
    with col_edit:

        content = st.text_area(
            "试题内容",
            height=220,
            placeholder="请输入题目正文（支持 Markdown / LaTeX / 图片）",
            key=f"upload_content_{key_suffix}"
        )

        answer = st.text_area(
            "答案",
            height=120,
            placeholder="请输入答案（支持 Markdown / LaTeX）",
            key=f"upload_answer_{key_suffix}"
        )

        analysis = st.text_area(
            "解析",
            height=180,
            placeholder="请输入解析（支持 Markdown / LaTeX）",
            key=f"upload_analysis_{key_suffix}"
        )

        left_year, right_type = st.columns(2)
        with left_year:
            year = st.number_input("年份", min_value=1949, max_value=2050, step=10, key=f"upload_year_{key_suffix}")
        with right_type:
            paper_type = st.text_input("卷种",
                placeholder="XX卷", key=f"upload_paper_type_{key_suffix}")

        left_no, right_type_op = st.columns(2)
        with left_no:
            question_no = st.text_input("题号", key=f"upload_question_no_{key_suffix}")
        with right_type_op:
            # 题型（自动检测预填，可手动修改）
            type_options = ["（未选择）"] + QUESTION_TYPES
            qt_key = f"upload_question_type_{key_suffix}"
            detected_type = detect_question_type(content, answer, question_no)
            if qt_key not in st.session_state and detected_type:
                st.session_state[qt_key] = detected_type
            question_type_sel = st.selectbox("题型", options=type_options, key=qt_key)
            question_type = None if question_type_sel == "（未选择）" else question_type_sel
            if detected_type:
                st.caption(f"💡 自动检测：{detected_type}（可修改）")
        
        # 知识模块（多选，可空）
        knowledge_modules = st.multiselect(
            "知识模块",
            options=KNOWLEDGE_MODULES,
            key=f"upload_knowledge_modules_{key_suffix}",
            placeholder="可多选",
        )

        left_source, right_analysis_source = st.columns(2)
        with left_source:
            source = st.text_input("题目来源", key=f"upload_source_{key_suffix}")
        with right_analysis_source:
            analysis_source = st.text_input("解析来源", key=f"upload_analysis_source_{key_suffix}")

    with col_preview:
        rich_markdown(IMAGE_DIR, True, None)

        st.divider()

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
            st.error("题目内容不能为空")
            return

        qid = create_question(
            content=content,
            answer=answer,
            analysis=analysis,
            source=source,
            analysis_source=analysis_source,
            year=year,
            paper_type=paper_type,
            question_no=question_no,
            question_type=question_type,
            knowledge_modules=knowledge_modules,
        )

        st.session_state["update_qid"] = qid

        st.session_state["form_version"] = key_suffix + 1
        
        st.session_state[f"upload_content_{key_suffix + 1}"] = ""
        st.session_state[f"upload_answer_{key_suffix + 1}"] = ""
        st.session_state[f"upload_analysis_{key_suffix + 1}"] = ""
        st.session_state[f"upload_source_{key_suffix + 1}"] = source
        st.session_state[f"upload_analysis_source_{key_suffix + 1}"] = analysis_source
        st.session_state[f"upload_year_{key_suffix + 1}"] = year
        st.session_state[f"upload_paper_type_{key_suffix + 1}"] = paper_type
        st.session_state[f"upload_question_no_{key_suffix + 1}"] = increment_number_in_string(question_no)

        st.rerun()
