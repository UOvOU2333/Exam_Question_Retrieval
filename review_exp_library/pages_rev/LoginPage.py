"""登录页组件。"""

import streamlit as st

from services_rev.AuthService import authenticate, set_current_user, clear_current_user, get_current_user
from utils_rev.permissions import role_display_name


def login():
    if st.session_state.get("rev_logged_in"):
        _show_logged_in()
        return

    st.subheader("登录")
    with st.form("rev_login_form", clear_on_submit=False):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录", type="primary", use_container_width=True)

    if submitted:
        ok, role, user_id = authenticate(username, password)
        if ok:
            from services_rev.AuthService import get_user_by_id
            u = get_user_by_id(user_id)
            set_current_user(user_id, u["username"], u["display_name"], u["role"])
            st.success("登录成功")
            st.rerun()
        else:
            st.error("用户名或密码错误")


def _show_logged_in():
    u = get_current_user()
    st.success(f"欢迎你，{u['display_name']}")
    left, right = st.columns([2, 1])
    with left:
        st.info(f"当前角色：**{role_display_name(u['role'])}**")
    with right:
        if st.button("退出登录"):
            clear_current_user()
            st.rerun()
