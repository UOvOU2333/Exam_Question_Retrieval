"""账号自助管理页：修改用户名 / 修改密码（验证当前密码）。"""

import streamlit as st

from services_rev.AuthService import get_current_user, require_login
from services_rev.MemberService import (
    verify_password, is_username_taken, update_username, update_password,
)
from utils_rev.exceptions import ValidationError, NotFoundError


def account_page():
    require_login()
    user = get_current_user()
    st.subheader("我的账号")

    st.markdown(f"当前用户名：**{user['username']}** ｜ 姓名：**{user['display_name']}**")

    with st.expander("修改用户名", expanded=False):
        with st.form("rev_change_username_form"):
            new_username = st.text_input("新用户名", value=user["username"], key="rev_new_uname")
            cur_pwd = st.text_input("当前密码（验证身份）", type="password", key="rev_uname_pwd")
            submitted = st.form_submit_button("保存用户名", type="primary")
        if submitted:
            if not new_username.strip():
                st.error("用户名不能为空")
            elif new_username.strip() == user["username"]:
                st.error("新用户名与当前相同")
            elif not verify_password(user["id"], cur_pwd):
                st.error("当前密码不正确")
            else:
                try:
                    update_username(user["id"], new_username.strip())
                    st.session_state["rev_username"] = new_username.strip()
                    st.success("用户名已更新")
                    st.rerun()
                except (ValidationError, NotFoundError) as e:
                    st.error(str(e))

    with st.expander("修改密码", expanded=False):
        with st.form("rev_change_pwd_form"):
            old_pwd = st.text_input("当前密码", type="password", key="rev_old_pwd")
            new_pwd = st.text_input("新密码", type="password", key="rev_new_pwd")
            new_pwd2 = st.text_input("确认新密码", type="password", key="rev_new_pwd2")
            submitted = st.form_submit_button("保存密码", type="primary")
        if submitted:
            if not verify_password(user["id"], old_pwd):
                st.error("当前密码不正确")
            elif new_pwd != new_pwd2:
                st.error("两次新密码不一致")
            elif not new_pwd.strip():
                st.error("新密码不能为空")
            else:
                try:
                    update_password(user["id"], new_pwd)
                    st.success("密码已更新")
                    st.rerun()
                except (ValidationError, NotFoundError) as e:
                    st.error(str(e))
