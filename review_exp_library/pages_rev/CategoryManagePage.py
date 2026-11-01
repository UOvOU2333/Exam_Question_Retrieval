"""分类体系管理页：四级独立实体（书名/问题与范例/案例类型/模块），每级单选框 + 右侧增加/重命名/删除按钮。"""

import streamlit as st

from services_rev.AuthService import get_current_user, require_permission
from services_rev.CatalogService import (
    list_books, list_sections, list_case_types, list_subjects,
    create_book, create_section, create_case_type, create_subject,
    rename_book, rename_section, rename_case_type, rename_subject,
    delete_book, delete_section, delete_case_type, delete_subject,
)
from utils_rev.exceptions import ValidationError, NotFoundError


def _render_level(nodes, label, user, key_prefix, on_create, on_rename, on_delete):
    if not nodes:
        st.info(f"暂无{label}，请先新增。")
        if st.button("增加", key=f"{key_prefix}_add", use_container_width=True):
            st.session_state[f"{key_prefix}_show_add"] = True
        node = None
    else:
        names = [n.name for n in nodes]
        col_list, col_ops = st.columns([7, 3])
        with col_list:
            sel = st.radio(label, names, horizontal=True, key=f"{key_prefix}_radio")
        node = next(n for n in nodes if n.name == sel)
        with col_ops:
            row_add, row_rn = st.columns(2)
            with row_add:
                if st.button("增加", key=f"{key_prefix}_add", use_container_width=True):
                    st.session_state[f"{key_prefix}_show_add"] = True
                    st.session_state.pop(f"{key_prefix}_show_rn", None)
            with row_rn:
                if st.button("重命名", key=f"{key_prefix}_rn", use_container_width=True):
                    st.session_state[f"{key_prefix}_show_rn"] = True
                    st.session_state.pop(f"{key_prefix}_show_add", None)
            with st.expander("其他操作"):
                if st.button("删除", key=f"{key_prefix}_del", type="primary", use_container_width=True):
                    try:
                        on_delete(node.id)
                        st.rerun()
                    except (ValidationError, NotFoundError) as e:
                        st.error(str(e))

    if st.session_state.get(f"{key_prefix}_show_add"):
        with st.form(f"{key_prefix}_add_form"):
            name = st.text_input(f"新{label}名称")
            left_sub, right_cancel = st.columns(2)
            with left_sub:
                sub = st.form_submit_button("确认增加", type="primary")
            with right_cancel:
                cancel = st.form_submit_button("取消")
        if sub:
            try:
                on_create(name)
                st.session_state.pop(f"{key_prefix}_show_add", None)
                st.rerun()
            except (ValidationError, NotFoundError) as e:
                st.error(str(e))
        if cancel:
            st.session_state.pop(f"{key_prefix}_show_add", None)
            st.rerun()

    if st.session_state.get(f"{key_prefix}_show_rn"):
        with st.form(f"{key_prefix}_rn_form"):
            name = st.text_input(f"{label}新名称", value=node.name)
            left_sub, right_cancel = st.columns(2)
            with left_sub:
                sub = st.form_submit_button("确认重命名", type="primary")
            with right_cancel:
                cancel = st.form_submit_button("取消")
        if sub:
            try:
                on_rename(node.id, name)
                st.session_state.pop(f"{key_prefix}_show_rn", None)
                st.rerun()
            except (ValidationError, NotFoundError) as e:
                st.error(str(e))
        if cancel:
            st.session_state.pop(f"{key_prefix}_show_rn", None)
            st.rerun()

    return node


def category_manage_page():
    require_permission("manage_catalog")
    user = get_current_user()
    st.subheader("分类体系管理")
    st.caption("四级独立实体：书名 / 问题与范例(全局共享) / 案例类型 / 模块(全局共享)。所有节点均可增删改。")

    books = list_books()
    book = _render_level(
        books, "书名", user, "l1_book",
        on_create=lambda n: create_book(n, operator_id=user["id"]),
        on_rename=lambda nid, n: rename_book(nid, n, operator_id=user["id"]),
        on_delete=lambda nid: delete_book(nid, operator_id=user["id"]),
    )
    if book is None:
        return

    sections = list_sections()
    section = _render_level(
        sections, "问题与范例", user, "l2_section",
        on_create=lambda n: create_section(n, operator_id=user["id"]),
        on_rename=lambda nid, n: rename_section(nid, n, operator_id=user["id"]),
        on_delete=lambda nid: delete_section(nid, operator_id=user["id"]),
    )
    if section is None:
        return

    case_types = list_case_types(section.id)
    case_type = _render_level(
        case_types, "案例类型", user, f"l3_ct_{section.id}",
        on_create=lambda n: create_case_type(n, section.id, operator_id=user["id"]),
        on_rename=lambda nid, n: rename_case_type(nid, n, operator_id=user["id"]),
        on_delete=lambda nid: delete_case_type(nid, operator_id=user["id"]),
    )
    if case_type is None:
        return

    subjects = list_subjects()
    _render_level(
        subjects, "模块", user, "l4_sub",
        on_create=lambda n: create_subject(n, operator_id=user["id"]),
        on_rename=lambda nid, n: rename_subject(nid, n, operator_id=user["id"]),
        on_delete=lambda nid: delete_subject(nid, operator_id=user["id"]),
    )
