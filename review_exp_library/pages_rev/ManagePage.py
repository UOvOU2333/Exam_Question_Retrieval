"""成员与分类管理页。"""

import streamlit as st

from services_rev.AuthService import get_current_user, require_permission
from services_rev.CatalogService import get_books, get_sections, get_case_types, get_subjects
from services_rev.MemberService import list_members, update_role, create_member
from utils_rev.exceptions import ValidationError, NotFoundError
from utils_rev.permissions import ROLE_EDITOR, ROLE_VIEWER, role_display_name


def manage_page():
    require_permission("manage_members")
    user = get_current_user()

    st.subheader("成员管理")
    members = list_members()
    for m in members:
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 3])
            with col1:
                st.markdown(f"**{m.display_name}**（{m.username}）")
            with col2:
                st.caption(role_display_name(m.role))
            with col3:
                if m.role == "chief":
                    st.caption("总编（不可变更）")
                else:
                    options = ["编辑", "浏览者"]
                    cur = "编辑" if m.role == ROLE_EDITOR else "浏览者"
                    new = st.selectbox(
                        "角色", options,
                        index=options.index(cur),
                        key=f"mg_role_{m.id}",
                    )
                    if new != cur:
                        target = ROLE_EDITOR if new == "编辑" else ROLE_VIEWER
                        try:
                            update_role(m.id, target, user["id"])
                            st.success("角色已更新")
                            st.rerun()
                        except (ValidationError, NotFoundError) as e:
                            st.error(str(e))

    st.markdown("### 新增成员")
    with st.form("add_member_form"):
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            new_username = st.text_input("账号")
        with col_b:
            new_pwd = st.text_input("密码", type="password")
        with col_c:
            new_disp = st.text_input("姓名")
        with col_d:
            new_role = st.selectbox("角色", ["编辑", "浏览者"], key="add_role")
        add_submitted = st.form_submit_button("新增")
    if add_submitted:
        if not new_username.strip() or not new_pwd.strip() or not new_disp.strip():
            st.error("账号/密码/姓名均不可为空")
        else:
            target = ROLE_EDITOR if new_role == "编辑" else ROLE_VIEWER
            try:
                create_member(new_username.strip(), new_pwd, new_disp.strip(), target, user["id"])
                st.success("成员已新增")
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    st.markdown("---")
    st.subheader("分类体系（只读）")
    st.markdown("**书名**")
    st.write(get_books())
    st.markdown("**一级板块**")
    st.write(get_sections())
    for sec in get_sections():
        st.markdown(f"- {sec}：{get_case_types(sec)}")
    st.markdown("**学科板块**")
    st.write(get_subjects())
