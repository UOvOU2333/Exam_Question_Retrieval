"""
试卷导出页面：选择年份 + 卷种，导出整套试卷（PDF / Word）。
"""

import streamlit as st

from utils.auth_utils import require_login, require_role
from utils.navbar_utils import navbar
from services.paper_export_services import (
    list_years_with_papers,
    list_paper_types_by_year,
    get_paper_questions,
)
from utils.export_utils import export_to_word, export_to_pdf


def export():
    # 登录校验 + 权限校验（仅 admin / editor 可导出，viewer 不可）
    require_login()
    require_role("admin", "editor")

    st.title("📤 试卷导出")
    st.caption("选择年份和卷种，导出整套试卷的题目、答案、解析（PDF / Word）")

    # ========================
    # 第一步：选择年份 + 卷种
    # ========================
    years = list_years_with_papers()
    if not years:
        st.warning("数据库中暂无题目")
        return

    col_year, col_paper = st.columns([1, 2])

    with col_year:
        selected_year = st.selectbox("年份", options=years, index=0)

    with col_paper:
        papers = list_paper_types_by_year(selected_year)
        if not papers:
            st.warning(f"{selected_year} 年暂无题目")
            return
        # 卷种下拉，显示"卷种名 (N题)"
        paper_options = [f"{p['paper_type']}（{p['count']} 题）" for p in papers]
        selected_paper_idx = st.selectbox(
            "卷种",
            options=range(len(papers)),
            format_func=lambda i: paper_options[i],
            index=0,
        )
        selected_paper = papers[selected_paper_idx]["paper_type"]
        selected_count = papers[selected_paper_idx]["count"]

    # ========================
    # 第二步：导出选项
    # ========================
    st.divider()

    col_fmt, col_opt1, col_opt2, col_opt3 = st.columns([1.2, 1, 1, 1])

    with col_fmt:
        export_format = st.radio(
            "导出格式",
            options=["PDF", "Word"],
            horizontal=True,
            key="export_format_radio",
        )

    with col_opt1:
        include_answer = st.toggle("含答案", value=True)
    with col_opt2:
        include_analysis = st.toggle("含解析", value=True)
    with col_opt3:
        include_source = st.toggle("含来源", value=False)

    # ========================
    # 第三步：预览题目列表
    # ========================
    st.divider()
    st.subheader(f"📋 {selected_year} {selected_paper}（共 {selected_count} 题）")

    questions = get_paper_questions(selected_year, selected_paper)
    if not questions:
        st.warning("未找到题目")
        return

    # 预览：题号 + 内容前 60 字
    with st.expander("预览题目列表", expanded=False):
        for q in questions:
            qno = q.get("question_no") or "?"
            content_preview = (q.get("content") or "").replace("\n", " ")[:60]
            st.write(f"**第 {qno} 题**：{content_preview}...")

    # ========================
    # 第四步：导出按钮
    # ========================
    paper_title = f"{selected_year} {selected_paper}"

    col_btn1, col_btn2, col_spacer = st.columns([1, 1, 3])
    with col_btn1:
        btn_export = st.button("📥 导出", type="primary", use_container_width=True)
    with col_btn2:
        btn_preview_doc = st.button("👁️ 预览文档内容", use_container_width=True)

    if btn_preview_doc:
        _show_content_preview(questions, include_answer, include_analysis, include_source)

    if btn_export:
        with st.spinner(f"正在生成 {export_format} 文件..."):
            try:
                if export_format == "Word":
                    file_bytes = export_to_word(
                        questions, paper_title,
                        include_answer=include_answer,
                        include_analysis=include_analysis,
                        include_source=include_source,
                    )
                    ext = "docx"
                    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                else:
                    file_bytes = export_to_pdf(
                        questions, paper_title,
                        include_answer=include_answer,
                        include_analysis=include_analysis,
                        include_source=include_source,
                    )
                    ext = "pdf"
                    mime = "application/pdf"

                filename = f"{paper_title}.{ext}"
                st.success(f"✅ {export_format} 文件生成成功！({len(file_bytes) / 1024:.1f} KB)")

                st.download_button(
                    label=f"⬇️ 下载 {filename}",
                    data=file_bytes,
                    file_name=filename,
                    mime=mime,
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"导出失败：{e}")


def _show_content_preview(questions, include_answer, include_analysis, include_source):
    """在页面上展示导出内容的纯文本预览。"""
    for idx, q in enumerate(questions, 1):
        qno = q.get("question_no") or str(idx)
        content = q.get("content") or ""
        answer = q.get("answer") or ""
        analysis = q.get("analysis") or ""
        source = q.get("source") or ""
        analysis_source = q.get("analysis_source") or ""

        with st.expander(f"第 {qno} 题", expanded=(idx == 1)):
            st.markdown("**【题目】**")
            st.markdown(content)

            if include_answer and answer:
                st.markdown("**【答案】**")
                st.markdown(answer)

            if include_analysis and analysis:
                st.markdown("**【解析】**")
                st.markdown(analysis)

            if include_source:
                parts = []
                if source:
                    parts.append(f"题目来源：{source}")
                if analysis_source and analysis_source != source:
                    parts.append(f"解析来源：{analysis_source}")
                if parts:
                    st.caption("；".join(parts))
