"""浏览与搜索页。"""

import streamlit as st

from pages_rev.CaseListComponent import render_case_list
from services_rev.AuthService import get_current_user, require_login
from services_rev.CaseService import list_cases
from services_rev.CatalogService import (
    get_books, get_sections, get_case_types, get_subjects,
)
from utils_rev.permissions import is_chief, is_editor


def _status_set_for(role, user_id):
    if is_chief(role):
        return {"已发布", "待总编审核", "已退回", "已归档"}
    if is_editor(role):
        return {"已发布", "已退回"}
    return {"已发布"}


def browse_page():
    require_login()
    user = get_current_user()
    role = user["role"]

    st.subheader("浏览与搜索")

    col_b, col_s, col_t, col_sub = st.columns(4)
    with col_b:
        book = st.selectbox("书名", ["全部"] + get_books(), key="br_book")
    with col_s:
        section = st.selectbox("一级板块", ["全部"] + get_sections(), key="br_section")
    with col_t:
        ct_options = ["全部"] + (get_case_types(section) if section != "全部" else [])
        case_type = st.selectbox("案例类型", ct_options, key="br_case_type")
    with col_sub:
        subject = st.selectbox("学科板块", ["全部"] + get_subjects(), key="br_subject")

    col_kw, col_sort, col_df, col_dt = st.columns([4, 2, 2, 2])
    with col_kw:
        keyword = st.text_input("搜索（题目/修改前后/理由/解析/注意事项）", key="br_kw")
    with col_sort:
        sort_by = st.selectbox(
            "排序", ["更新时间", "上传时间", "审稿时间"], key="br_sort",
        )
    with col_df:
        date_from = st.date_input("起（审稿时间）", value=None, key="br_df")
    with col_dt:
        date_to = st.date_input("止（审稿时间）", value=None, key="br_dt")

    sort_map = {"更新时间": "update_time", "上传时间": "upload_time", "审稿时间": "review_time"}
    sort_field = sort_map.get(sort_by, "update_time")

    book_q = None if book == "全部" else book
    section_q = None if section == "全部" else section
    ct_q = None if case_type == "全部" else case_type
    sub_q = None if subject == "全部" else subject
    kw = keyword.strip() or None

    if is_chief(role):
        summaries, total = list_cases(
            book=book_q, section=section_q, case_type=ct_q, subject=sub_q,
            keyword=kw, status_set={"已发布", "待总编审核", "已退回", "已归档"},
            sort_by=sort_field, date_from=date_from, date_to=date_to,
            page=1, page_size=200,
        )
    elif is_editor(role):
        pub, t1 = list_cases(
            book=book_q, section=section_q, case_type=ct_q, subject=sub_q,
            keyword=kw, status_set={"已发布"},
            sort_by=sort_field, date_from=date_from, date_to=date_to,
            page=1, page_size=200,
        )
        mine, t2 = list_cases(
            book=book_q, section=section_q, case_type=ct_q, subject=sub_q,
            keyword=kw, status_set={"草稿", "已退回"}, owner_id=user["id"],
            sort_by=sort_field, date_from=date_from, date_to=date_to,
            page=1, page_size=200,
        )
        summaries = pub + mine
        total = t1 + t2
    else:
        summaries, total = list_cases(
            book=book_q, section=section_q, case_type=ct_q, subject=sub_q,
            keyword=kw, status_set={"已发布"},
            sort_by=sort_field, date_from=date_from, date_to=date_to,
            page=1, page_size=200,
        )

    summaries.sort(key=lambda x: x.update_time, reverse=True)

    st.caption(f"共 {total} 条")
    render_case_list(summaries)
