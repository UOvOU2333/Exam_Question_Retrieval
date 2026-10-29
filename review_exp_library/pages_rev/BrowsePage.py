"""浏览与搜索页（分类 ID 驱动）。"""

import streamlit as st

from pages_rev.CaseListComponent import render_case_list
from services_rev.AuthService import get_current_user, require_login
from services_rev.CaseService import list_cases
from services_rev.CatalogService import list_books, list_sections, list_case_types, list_subjects
from utils_rev.permissions import is_chief, is_editor


def browse_page():
    require_login()
    user = get_current_user()
    role = user["role"]

    st.subheader("浏览与搜索")

    col_b, col_s, col_t, col_sub = st.columns(4)
    with col_b:
        book_options = [(0, "全部")] + [(b.id, b.name) for b in list_books()]
        book_id = st.selectbox("书名", book_options, format_func=lambda x: x[1], key="br_book")[0]
    with col_s:
        section_options = [(0, "全部")] + [(s.id, s.name) for s in list_sections()]
        section_id = st.selectbox("板块", section_options, format_func=lambda x: x[1], key="br_section")[0]
    with col_t:
        ct_options = [(0, "全部")]
        if section_id != 0:
            for ct in list_case_types(section_id):
                ct_options.append((ct.id, ct.name))
        case_type_id = st.selectbox("案例类型", ct_options, format_func=lambda x: x[1], key="br_case_type")[0]
    with col_sub:
        sub_options = [(0, "全部")]
        for sub in list_subjects():
            sub_options.append((sub.id, sub.name))
        subject_id = st.selectbox("学科", sub_options, format_func=lambda x: x[1], key="br_subject")[0]

    col_kw, col_sort, col_df, col_dt = st.columns([4, 2, 2, 2])
    with col_kw:
        keyword = st.text_input("搜索（题目/修改前后/理由/解析/注意事项）", key="br_kw")
    with col_sort:
        sort_by = st.selectbox("排序", ["更新时间", "上传时间", "审稿时间"], key="br_sort")
    with col_df:
        date_from = st.date_input("起（审稿时间）", value=None, key="br_df")
    with col_dt:
        date_to = st.date_input("止（审稿时间）", value=None, key="br_dt")

    sort_map = {"更新时间": "update_time", "上传时间": "upload_time", "审稿时间": "review_time"}
    sort_field = sort_map.get(sort_by, "update_time")

    bq = None if book_id == 0 else book_id
    sq = None if section_id == 0 else section_id
    cq = None if case_type_id == 0 else case_type_id
    uq = None if subject_id == 0 else subject_id
    kw = keyword.strip() or None

    if is_chief(role):
        summaries, total = list_cases(
            book_id=bq, section_id=sq, case_type_id=cq, subject_id=uq,
            keyword=kw, status_set={"已发布", "待总编审核", "已退回", "已归档"},
            sort_by=sort_field, date_from=date_from, date_to=date_to,
            page=1, page_size=200,
        )
    elif is_editor(role):
        pub, t1 = list_cases(
            book_id=bq, section_id=sq, case_type_id=cq, subject_id=uq,
            keyword=kw, status_set={"已发布"},
            sort_by=sort_field, date_from=date_from, date_to=date_to,
            page=1, page_size=200,
        )
        mine, t2 = list_cases(
            book_id=bq, section_id=sq, case_type_id=cq, subject_id=uq,
            keyword=kw, status_set={"草稿", "已退回"}, owner_id=user["id"],
            sort_by=sort_field, date_from=date_from, date_to=date_to,
            page=1, page_size=200,
        )
        summaries = pub + mine
        total = t1 + t2
    else:
        summaries, total = list_cases(
            book_id=bq, section_id=sq, case_type_id=cq, subject_id=uq,
            keyword=kw, status_set={"已发布"},
            sort_by=sort_field, date_from=date_from, date_to=date_to,
            page=1, page_size=200,
        )

    summaries.sort(key=lambda x: x.update_time, reverse=True)

    st.caption(f"共 {total} 条")
    render_case_list(summaries)
