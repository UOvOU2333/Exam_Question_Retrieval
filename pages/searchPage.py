import streamlit as st
import streamlit_antd_components as sac
from time import sleep

from utils.auth_utils import require_login, check_permission
from utils.permissions import is_admin
from utils.render_utils import render_markdown
from utils.note_utils import display_notes_list
from utils.kb_utils import display_kb_capsules
from services.question_services import search_questions, get_question_by_id, get_question_summaries, search_by_note
from services.note_services import get_all_note_types, get_visible_note_type_ids
from tools.exam_type_utils import QUESTION_TYPES, KNOWLEDGE_MODULES, str_to_knowledge_modules


def search():
    # ===== 登录校验（viewer 也允许）=====
    require_login()

    col_title, col_show, col_tag = st.columns([2, 1.25, 1.5])

    with col_title:
        st.title("📚 试题检索")

    with col_show:
        show_choice = st.radio(
            "搜索项",
            options=["隐藏", "基础", "高级"],
            horizontal=True,
            key="if_show_radio"
        )

    if show_choice == "基础":
        with col_tag:
            col_filter, col_copy = st.columns(2)
            with col_filter:
                flag_no = False
            with col_copy:
                flag_copy = st.toggle("复制模式")
                flag_new_textbook = st.toggle("新教材")

        years, paper_type, question_no, question_type_filter, knowledge_modules_filter, \
            field_que, field_sou, search_scope = _render_base_filters()

        type_id = None
        note_content = ""
        note_creator = ""

    elif show_choice == "高级":
        with col_tag:
            flag_copy = st.toggle("复制模式")

        # 主区域：纯备注检索
        st.subheader("📝 备注检索")
        type_id, note_content, note_creator = _render_note_filters()

        # 附属功能：同时按题目条件过滤（与备注结果取交集）
        with st.expander("同时按题目条件过滤（可选）", expanded=False):
            st.caption("以下条件留空则不限制；填写后将与备注检索结果取交集")
            flag_new_textbook = st.toggle("仅看新教材", key="adv_new_textbook")
            years, paper_type, question_no, question_type_filter, knowledge_modules_filter, \
                field_que, field_sou, search_scope = _render_base_filters()

        flag_no = False
    else:
        with col_tag:
            col_filter, col_copy = st.columns(2)
            with col_copy:
                flag_copy = st.toggle("复制模式")
        flag_new_textbook = False
        flag_no = False
        years = []
        paper_type = ""
        question_no = ""
        field_que = "all"
        field_sou = "all"
        search_scope = "题目/答案/解析"
        question_type_filter = "（不限）"
        knowledge_modules_filter = []
        type_id = None
        note_content = ""
        note_creator = ""

    keyword = st.text_input(
        "关键词检索",
        placeholder="请输入关键词",
    )

    # =========================
    # 执行检索
    # =========================
    if show_choice == "高级":
        # 高级模式以备注检索为主，必须至少填一个备注条件
        if not (type_id or note_content.strip() or note_creator.strip()):
            st.info("请输入备注检索条件开始检索")
            return

        # 按当前用户可见类型过滤备注检索结果（admin 不过滤）
        _viewer_role = st.session_state.get("role")
        _visible_ids = None if (not _viewer_role or is_admin(_viewer_role)) \
            else get_visible_note_type_ids(_viewer_role)
        note_results = search_by_note(
            type_id=type_id or None,
            content=note_content.strip() or None,
            created_by=note_creator.strip() or None,
            fuzzy=True,
            visible_type_ids=_visible_ids
        )

        # 附属：若同时填了基础条件，则与备注结果取交集
        if _has_base_filters(years, paper_type, question_no, keyword,
                             knowledge_modules_filter, question_type_filter, flag_new_textbook):
            base_results = search_questions(
                paper_type=paper_type.strip() or None,
                question_no=question_no.strip() or None,
                keyword=keyword.strip() or None,
                years=years,
                field_que=field_que,
                field_sou=field_sou,
                search_scope="qa" if search_scope == "题目/答案/解析" else "source",
                no_fuzzy=flag_no,
                new_textbook_only=flag_new_textbook,
                question_type=question_type_filter if question_type_filter != "（不限）" else None,
                knowledge_modules=knowledge_modules_filter or None,
            )
            _base_set = set(base_results)
            results = [i for i in note_results if i in _base_set]
        else:
            results = note_results
    else:
        # 基础检索
        if (not paper_type.strip() and not question_no.strip() and not keyword.strip()
                and not years and not flag_new_textbook and not knowledge_modules_filter
                and question_type_filter == "（不限）"):
            st.info("请输入搜索条件开始检索")
            return

        results = search_questions(
            paper_type=paper_type.strip() or None,
            question_no=question_no.strip() or None,
            keyword=keyword.strip() or None,
            years=years,
            field_que=field_que,
            field_sou=field_sou,
            search_scope="qa" if search_scope == "题目/答案/解析" else "source",
            no_fuzzy=flag_no,
            new_textbook_only=flag_new_textbook,
            question_type=question_type_filter if question_type_filter != "（不限）" else None,
            knowledge_modules=knowledge_modules_filter or None,
        )

    st.divider()

    # =========================
    # 检索结果展示
    # =========================
    if not results:
        st.warning("未找到相关试题")
        return

    st.success(f"共找到 {len(results)} 条结果")

    summaries = get_question_summaries(results)
    # 只是内部划分执行范围，所有结果仍连续显示，不改变列表或增加分页。
    for offset in range(0, len(summaries), 50):
        _render_search_results(summaries[offset:offset + 50], flag_copy, keyword)
        if offset + 50 < len(summaries):
            # Streamlit 的 WebSocket 发送队列有界。给消息发送任务让出时间，
            # 避免全量结果一次涌入队列导致会话断开、展开空白及导航失效。
            sleep(0.02)


def _render_base_filters():
    """渲染基础检索条件（年份/卷种/题号/题型/知识模块/搜索范围/关键词），返回各条件值。"""
    col_year, col_type, col_no = st.columns([5, 2, 2])

    with col_year:
        years = st.multiselect(
            "年份",
            options=list(range(1949, 2050)),
            placeholder="可多选",
            key="base_years",
        )

    with col_type:
        paper_type = st.text_input(
            "卷种",
            placeholder="请输入卷种",
            key="base_paper_type",
        )

    with col_no:
        question_no = st.text_input(
            "题号",
            placeholder="请输入题号",
            key="base_question_no",
        )

    col_qtype, col_km = st.columns([1, 2])
    with col_qtype:
        question_type_filter = st.selectbox(
            "题型",
            options=["（不限）"] + QUESTION_TYPES,
            key="search_question_type",
        )
    with col_km:
        knowledge_modules_filter = st.multiselect(
            "知识模块",
            options=KNOWLEDGE_MODULES,
            placeholder="可多选",
            key="search_knowledge_modules",
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

    # 体验用户不可搜索/查看解析，仅保留题目与答案选项
    if not check_permission("view_analysis"):
        options_que = [o for o in options_que if o[1] in ("content", "answer")]
        options_sou = [o for o in options_sou if o[1] == "source"]

    col_cho, col_op = st.columns([1, 1])

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

    return (years, paper_type, question_no, question_type_filter, knowledge_modules_filter,
            field_que, field_sou, search_scope)


def _render_note_filters():
    """渲染备注检索条件（标签/备注内容/备注人），返回 (type_id, note_content, note_creator)。"""
    viewer_role = st.session_state.get("role")
    note_types = get_all_note_types()
    if viewer_role and not is_admin(viewer_role):
        visible_ids = set(get_visible_note_type_ids(viewer_role))
        note_types = [t for t in note_types if t['id'] in visible_ids]
    note_type_options = {"全部标签": None}
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

    return type_id, note_content, note_creator


def _has_base_filters(years, paper_type, question_no, keyword,
                      knowledge_modules_filter, question_type_filter, flag_new_textbook):
    """判断是否填写了任何基础检索条件（用于高级模式决定是否与备注结果取交集）。"""
    return bool(
        years
        or paper_type.strip()
        or question_no.strip()
        or keyword.strip()
        or knowledge_modules_filter
        or question_type_filter != "（不限）"
        or flag_new_textbook
    )


@st.fragment
def _render_search_results(summaries, flag_copy, keyword):
    # 展开一题只重跑所在的这一小组，不重新检索或重建全部结果。
    for summary in summaries:
        _render_question_result(summary, flag_copy, keyword)


def _render_question_result(summary, flag_copy, keyword):
    qid = summary["questionID"]
    year = summary["year"]
    paper_type = summary["paper_type"]
    question_no = summary["question_no"]
    q_type = summary["question_type"]

    tip_parts = []
    if year:
        tip_parts.append(f"年份：{year}")
    if paper_type:
        tip_parts.append(f"卷种：{paper_type}")
    if question_no:
        tip_parts.append(f"题号：{question_no}")
    if q_type:
        tip_parts.append(f"题型：{q_type}")

    tip_parts_in_que = []
    if year:
        tip_parts_in_que.append(f"{year}")
    if paper_type:
        tip_parts_in_que.append(f"{paper_type}")
    if question_no:
        tip_parts_in_que.append(f" · T{question_no}")

    tip_in_que = ""
    if tip_parts_in_que:
        tip_in_que = "".join(tip_parts_in_que)
        tip_in_que = f"（{tip_in_que}）"

    # 保留原有折叠框外观，展开事件仅用于驱动按需读取和渲染。
    expander = st.expander(
        f"📘 题目 #{qid}" + " | " + " | ".join(tip_parts),
        expanded=False,
        key=f"search_detail_{qid}",
        on_change="rerun",
    )
    with expander:
        if not expander.open:
            return

        q = get_question_by_id(qid)
        if not q or q["isInRecycleBin"]:
            st.warning("题目不存在或已移入回收站")
            return
        content = q["content"]
        answer = q["answer"]
        analysis = q["analysis"]
        source = q["source"]
        analysis_source = q["analysis_source"]
        q_km = q["knowledge_modules"]

        caption_parts = []

        if flag_copy:
            render_markdown(content, tip_in_que, keyword)
            if answer:
                render_markdown(answer, "【答案】", keyword)
            if analysis:
                if check_permission("view_analysis"):
                    render_markdown(analysis, "【解析】", keyword)
                else:
                    st.info("🔒 当前为体验用户，无法查看解析内容")

        else:
            st.markdown("### 题目内容")
            render_markdown(content, None, keyword)

            if answer:
                st.markdown("### 答案")
                render_markdown(answer, None, keyword)

            if analysis:
                if check_permission("view_analysis"):
                    st.markdown("### 解析")
                    render_markdown(analysis, None, keyword)
                else:
                    st.info("🔒 当前为体验用户，无法查看解析内容")

            if year:
                caption_parts.append(f"📅 年份：{year}")
            if paper_type:
                caption_parts.append(f"📥 卷种：{paper_type}")
            if question_no:
                caption_parts.append(f"📑 题号：{question_no}")

        if q_km:
            caption_parts.append(f"📚 知识模块：{q_km}")
        if source:
            caption_parts.append(f"📌 来源：{source}")
        if analysis_source:
            caption_parts.append(f"🔍 解析来源：{analysis_source}")
        if caption_parts:
            st.caption(" | ".join(caption_parts))

        display_notes_list(qid)

        display_kb_capsules(qid)

        if check_permission("update"):
            if st.button("更新试题", key=f"update_btn_{qid}"):
                st.session_state["update_qid"] = qid
                st.switch_page("pages/managingPage.py")
