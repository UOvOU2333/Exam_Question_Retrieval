import streamlit as st

from utils.auth_utils import require_login
from utils.render_utils import render_markdown
from services.question_services import search_questions
from pages.updatePage import update_question


def search():
    # ===== 登录校验（viewer 也允许）=====
    require_login()

    st.title("📚 试题检索")

    # =========================
    # 检索输入区
    # =========================
    keyword = st.text_input(
        "🔍 关键词检索（支持模糊匹配）",
        placeholder="可搜索题目 / 答案 / 解析中的任意关键词"
    )

    if not keyword.strip():
        st.info("请输入关键词开始检索")
        return

    # =========================
    # 执行检索
    # =========================
    results = search_questions(keyword.strip())

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

        with st.expander(f"📘 题目 #{qid}", expanded=False):

            st.markdown("### 题目内容")
            render_markdown(content)

            if answer:
                st.markdown("### 答案")
                render_markdown(answer)

            if analysis:
                st.markdown("### 解析")
                render_markdown(analysis)

            if source:
                st.caption(f"📌 来源：{source}")

            if st.button("更新试题", key=f"update_btn_{qid}"):
                update_question(qid)
