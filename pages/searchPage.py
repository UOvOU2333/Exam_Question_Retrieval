import streamlit as st
import streamlit_antd_components as sac

from utils.auth_utils import require_login
from utils.render_utils import render_markdown
from utils.note_utils import display_notes_list
from services.question_services import search_questions, get_question_by_id, search_by_note
from services.note_services import get_all_note_types


def search():
    # ===== 登录校验（viewer 也允许）=====
    require_login()

    col_title, col_show, col_tag = st.columns([2,2,1])

    with col_title: 
        st.title("📚 试题检索")

    with col_show:
        show_choice = st.radio(
            "搜索项",
            options=["隐藏", "基础", "高级"],
            horizontal=True,
            key="if_show_radio"
        )

    if show_choice != "隐藏":

        # with col_tag:
        #     flag_type = st.toggle("卷种精确")
        #     flag_no = st.toggle("题号精确")
        # =========================
        # 检索输入区
        # =========================

        col_year, col_type, col_no = st.columns([5,2,2])

        with col_year:
            years = st.multiselect(
                "年份",
                options=list(range(2000, 2031)),
                placeholder="可多选"
            )

        with col_type:
            paper_type = st.text_input(
                "卷种",
                placeholder="请输入卷种"
            )

        with col_no:
            question_no = st.text_input(
                "题号",
                placeholder="请输入题号"
            )

        options_que = [
            ("全部字段", "all"),
            ("题目内容", "content"),
            ("答案", "answer"),
            ("解析", "analysis"),
        ]

        options_sou = [
            ("全部字段", "all"),
            ("题目来源", "source"),
            ("解析来源", "analysis_source"),
        ]

        col_cho, col_op = st.columns([1,1])

        with col_cho:
            search_scope = st.radio(
                "搜索范围",
                options=["题目/答案/解析", "题目来源/解析来源"],
                horizontal=True,
                key="search_scope_radio"
            )

        with col_op:
            st.space()
            if search_scope == "题目/答案/解析":
                selected_index_que = sac.segmented(
                    items=[sac.SegmentedItem(label=o[0]) for o in options_que],
                    align="start",
                    size="md",
                    return_index=True,
                    key="segmented_que",
                    use_container_width=True
                )
                field_que = options_que[selected_index_que][1]
                field_sou = "all"

            else:
                selected_index_sou = sac.segmented(
                    items=[sac.SegmentedItem(label=o[0]) for o in options_sou],
                    align="start",
                    size="md",
                    return_index=True,
                    key="segmented_sou",
                    use_container_width=True
                )
                field_sou = options_sou[selected_index_sou][1]
                field_que = "all"

        if show_choice == "高级":
            st.subheader("📝 备注检索")
            
            # 获取所有标签（笔记类型）
            note_types = get_all_note_types()
            note_type_options = {"": None}
            for note_type in note_types:
                note_type_options[note_type['type_name']] = note_type['id']
            
            col_tag, col_content, col_creator = st.columns(3)
            
            with col_tag:
                selected_tag = st.selectbox(
                    "标签",
                    options=list(note_type_options.keys()),
                    placeholder="选择标签",
                    key="note_tag"
                )
                type_id = note_type_options.get(selected_tag)
            
            with col_content:
                note_content = st.text_input(
                    "备注内容",
                    placeholder="输入备注内容关键词",
                    key="note_content"
                )
            
            with col_creator:
                note_creator = st.text_input(
                    "备注人",
                    placeholder="输入备注人关键词",
                    key="note_creator"
                )

    else:
        years = []
        paper_type = ""
        question_no = ""
        field_que = "all"
        field_sou = "all"
        search_scope = "题目/答案/解析"
        type_id = None
        note_content = ""
        note_creator = ""

    keyword = st.text_input(
        "关键词检索",
        placeholder="请输入关键词"
    )

    if not paper_type.strip() and not question_no.strip() and not keyword.strip() and not years:
        st.info("请输入搜索条件开始检索")
        return

    # =========================
    # 执行检索
    # =========================
    # 基础检索
    base_results = search_questions(
        paper_type=paper_type.strip() or None,
        question_no=question_no.strip() or None,
        keyword=keyword.strip() or None,
        years=years,
        field_que=field_que,
        field_sou=field_sou,
        search_scope="qa" if search_scope == "题目/答案/解析" else "source",
        fuzzy=True
    )
    
    # 备注检索（如果有备注检索条件）
    note_results = []
    if show_choice == "高级":
    # if type_id or note_content or note_creator:
        note_results = search_by_note(
            type_id=type_id,
            content=note_content.strip() or None,
            created_by=note_creator.strip() or None,
            fuzzy=True
        )
    
    # 取交集
    if note_results:
        results = list(set(base_results) & set(note_results))
    else:
        results = base_results

    st.divider()

    # =========================
    # 检索结果展示
    # =========================
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

            if st.button("更新试题", key=f"update_btn_{qid}"):
                st.session_state["update_qid"] = qid
                st.switch_page("pages/managingPage.py")
            