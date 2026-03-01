import streamlit as st
import streamlit_antd_components as sac

from utils.auth_utils import require_login
from utils.render_utils import render_markdown
from services.question_services import search_questions
from pages.updatePage import update_page


def search():
    # ===== 登录校验（viewer 也允许）=====
    require_login()

    col_title, col_year = st.columns([1,1])

    with col_title: 
        st.title("📚 试题检索")

    with col_year:
        years = st.multiselect(
            "年份",
            options=list(range(2000, 2031)),
            placeholder="可多选"
        )

    # =========================
    # 检索输入区
    # =========================

    options = [
        ("全部字段", "all"),
        ("卷种", "paper_type"),
        ("题号", "question_no"),
        ("题目内容", "content"),
        ("题目来源", "source"),
        ("答案", "answer"),
        ("解析", "analysis"),
        ("解析来源", "analysis_source"),
    ]

    selected_index = sac.segmented(
        items=[sac.SegmentedItem(label=o[0]) for o in options],
        align="start",
        size="md",
        return_index=True
    )

    field = options[selected_index][1]

    keyword = st.text_input(
        "🔍 关键词检索（支持模糊匹配）",
        placeholder="可搜索题目 / 答案 / 解析中的任意关键词"
    )

    if not keyword.strip() and not years:
        st.info("请输入关键词或选择年份开始检索")
        return

    # =========================
    # 执行检索
    # =========================
    results = search_questions(keyword=keyword.strip(), field=field, years=years)

    st.divider()

    # =========================
    # 检索结果展示
    # =========================
    if not results:
        st.warning("未找到相关试题")
        return

    st.success(f"共找到 {len(results)} 条结果")

    for q in results:
        qid = q["questionID"]
        content = q["content"]
        answer = q["answer"]
        analysis = q["analysis"]
        source = q["source"]
        analysis_source = q["analysis_source"],
        year = q["year"],
        paper_type = q["paper_type"],
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

            if year:
                if  paper_type:
                    st.caption(f"📅 年份卷种：{year} {paper_type}")
                else:
                    st.caption(f"📅 年份：{year}")
            else:
                if paper_type:
                    st.caption(f"📑 卷种：{paper_type}")

            if source:
                if question_no:
                    st.caption(f"📌 来源：{source} {question_no}")
                else:
                    st.caption(f"📌 来源：{source}")
            
            if analysis_source:
                    st.caption(f"🔍 解析来源：{analysis_source}")
                    

            if st.button("更新试题", key=f"update_btn_{qid}"):
                update_page(qid)
