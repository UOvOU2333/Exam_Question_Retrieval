"""成员管理页：参考题库 pages/userManagePage.py 风格。"""

from turtle import left

import streamlit as st

from services_rev.AuthService import get_current_user, require_permission
from services_rev.MemberService import (
    list_members, create_member, update_role,
    soft_delete_user, restore_user, delete_user,
)
from utils_rev.exceptions import ValidationError, NotFoundError
from utils_rev.permissions import (
    ROLE_ADMIN, ROLE_CHIEF, ROLE_EDITOR, ROLE_VIEWER, ALL_ROLES,
    ROLE_NAMES, ROLE_EN_SHORT, role_display_name, is_admin,
)


@st.dialog("确认永久删除", width="small")
def _permanent_delete_confirm_dialog(uid, uname):
    st.warning(f"确定要永久删除用户 {uname}（ID {uid}）吗？此操作不可恢复！")
    col_c, col_d = st.columns(2)
    with col_c:
        if st.button("确定删除", key=f"pd_yes_{uid}", type="primary"):
            try:
                user = get_current_user()
                delete_user(uid, user["id"])
                st.success("已永久删除")
                st.rerun()
            except (ValidationError, NotFoundError) as e:
                st.error(str(e))
    with col_d:
        if st.button("取消", key=f"pd_no_{uid}"):
            st.rerun()


def manage_page():
    require_permission("manage_members")
    user = get_current_user()
    admin_mode = is_admin(user["role"])

    st.subheader("成员管理")

    members = list_members(include_deleted=True)

    st.markdown("#### 用户列表")
    header_cols = st.columns([1, 2, 2, 2, 2, 3])
    for col, txt in zip(header_cols, ["ID", "用户名", "姓名", "角色", "状态", "操作"]):
        col.markdown(f"**{txt}**")

    for m in members:
        cols = st.columns([1, 2, 2, 2, 2, 3])
        with cols[0]:
            st.markdown(str(m.id))
        with cols[1]:
            st.markdown(m.username)
        with cols[2]:
            st.markdown(m.display_name)
        with cols[3]:
            st.markdown(f"{role_display_name(m.role)}（{ROLE_EN_SHORT.get(m.role, m.role)}）")
        with cols[4]:
            st.markdown("已禁用" if m.is_deleted else "正常")
        with cols[5]:
            if m.role == ROLE_ADMIN and m.id == user["id"]:
                st.caption("管理员（保护）")
            elif m.role == ROLE_CHIEF and not admin_mode:
                st.caption("总编（保护）")
            elif m.is_deleted:
                col_r, col_d = st.columns(2)
                with col_r:
                    if st.button("恢复", key=f"rs_{m.id}", type="primary"):
                        try:
                            restore_user(m.id, user["id"])
                            st.success("已恢复")
                            st.rerun()
                        except (ValidationError, NotFoundError) as e:
                            st.error(str(e))
                with col_d:
                    if st.button("永久删除", key=f"pd_{m.id}"):
                        _permanent_delete_confirm_dialog(m.id, m.username)
            else:
                left_part, right_part = st.columns([1,2])
                with left_part:
                    if st.button("禁用", key=f"dis_{m.id}"):
                        try:
                            soft_delete_user(m.id, user["id"])
                            st.success("已禁用")
                            st.rerun()
                        except (ValidationError, NotFoundError) as e:
                            st.error(str(e))
                with right_part:
                    role_options = list(ALL_ROLES)
                    if not admin_mode:
                        role_options = [r for r in role_options if r not in (ROLE_ADMIN, ROLE_CHIEF)]
                    role_labels = {r: f"{ROLE_NAMES[r]}（{ROLE_EN_SHORT[r]}）" for r in role_options}
                    cur_idx = role_options.index(m.role) if m.role in role_options else 0
                    new_role = st.selectbox(
                        "角色", role_options,
                        index=cur_idx,
                        format_func=lambda r: role_labels[r],
                        key=f"role_sb_{m.id}",
                        label_visibility="collapsed",
                    )
                if new_role != m.role:
                    try:
                        update_role(m.id, new_role, user["id"])
                        st.success("角色已更新")
                        st.rerun()
                    except (ValidationError, NotFoundError) as e:
                        st.error(str(e))

    st.markdown("---")
    st.markdown("#### 新增成员")
    with st.form("add_member_form"):
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            new_username = st.text_input("账号")
        with col_b:
            new_pwd = st.text_input("密码", type="password")
        with col_c:
            new_disp = st.text_input("姓名")
        with col_d:
            add_role_options = ["管理员", "总编", "编辑", "浏览者"] if admin_mode else ["编辑", "浏览者"]
            new_role_label = st.selectbox("角色", add_role_options, key="add_role_label")
        add_submitted = st.form_submit_button("新增", type="primary")
    if add_submitted:
        if new_role_label == "管理员":
            target = ROLE_ADMIN
        elif new_role_label == "总编":
            target = ROLE_CHIEF
        elif new_role_label == "编辑":
            target = ROLE_EDITOR
        else:
            target = ROLE_VIEWER
        try:
            create_member(new_username, new_pwd, new_disp, target, user["id"])
            st.success("成员已新增")
            st.rerun()
        except ValidationError as e:
            st.error(str(e))
