# authPage.py
import streamlit as st

from services.user_services import (
    authenticate,
    is_ai_enabled,
    verify_password,
    is_username_taken,
    update_username,
    update_password,
)
from utils.permissions import ROLE_NAMES, ROLE_PERMISSION_INFO


# ========== 登录页 / 用户主页 ==========
def login():
    st.title("用户中心")

    # ===== 已登录：用户主页 =====
    if st.session_state.get("logged_in"):
        show_dashboard()
        return

    # ===== 未登录：登录表单 =====
    st.subheader("登录")

    # ===== 使用 form 支持回车提交 =====
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")

        st.space()

        submitted = st.form_submit_button(
            "登录",
            type="primary",
            use_container_width=True
        )

    if submitted:
        ok, role, user_id = authenticate(username, password)
        if ok:
            st.session_state["user_id"] = user_id
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["role"] = role
            st.success("登录成功")
            st.rerun()
        else:
            st.error("用户名或密码错误")


# ========== 用户主页 ==========
def show_dashboard():
    username = st.session_state["username"]
    role = st.session_state["role"]

    st.success(f"欢迎你，{username}")

    info = ROLE_PERMISSION_INFO.get(role, "查看试题")
    role_cn = ROLE_NAMES.get(role, role)
    ai_ok = is_ai_enabled(st.session_state.get("user_id"))
    ai_text = "可使用" if ai_ok else "未授权"
    left, mid, right = st.columns([1, 2, 1])
    with left:
        st.info(f"当前角色：**{role_cn}**")
    with mid:
        st.info(f"你的权限：**{info}**")
    with right:
        st.info(f"智能助手：**{ai_text}**")

    # ===== 用户信息管理 =====
    show_account_settings()

    # ===== 退出 =====
    if st.button("退出登录"):
        for k in ["logged_in", "username", "role"]:
            st.session_state.pop(k, None)
        st.rerun()


# ========== 用户信息自助管理 ==========
def show_account_settings():
    user_id = st.session_state.get("user_id")
    username = st.session_state.get("username")

    with st.expander("账号设置", expanded=False):
        left, right = st.columns(2)
        with left:
            # ----- 修改用户名 -----
            with st.form("change_username_form"):
                st.subheader("修改用户名")
                new_username = st.text_input("新用户名", value=username)
                cur_pwd_for_name = st.text_input("当前密码（验证身份）", type="password", key="pwd_for_username")
                name_submitted = st.form_submit_button("保存用户名", use_container_width=True)

            if name_submitted:
                if not new_username.strip():
                    st.error("用户名不能为空")
                elif new_username.strip() == username:
                    st.warning("新用户名与当前相同")
                elif not verify_password(user_id, cur_pwd_for_name):
                    st.error("当前密码不正确")
                elif is_username_taken(new_username.strip(), exclude_user_id=user_id):
                    st.error("该用户名已被占用，请换一个")
                else:
                    update_username(user_id, new_username.strip())
                    st.session_state["username"] = new_username.strip()
                    st.success("用户名修改成功")
                    st.rerun()
        with right:
            # ----- 修改密码 -----
            with st.form("change_password_form"):
                st.subheader("修改密码")
                cur_pwd = st.text_input("当前密码", type="password", key="pwd_cur")
                new_pwd = st.text_input("新密码", type="password", key="pwd_new")
                confirm_pwd = st.text_input("确认新密码", type="password", key="pwd_confirm")
                pwd_submitted = st.form_submit_button("保存密码", use_container_width=True)

            if pwd_submitted:
                if not verify_password(user_id, cur_pwd):
                    st.error("当前密码不正确")
                elif not new_pwd:
                    st.error("新密码不能为空")
                elif new_pwd != confirm_pwd:
                    st.error("两次输入的新密码不一致")
                elif new_pwd == cur_pwd:
                    st.warning("新密码不能与当前密码相同")
                else:
                    update_password(user_id, new_pwd)
                    st.success("密码修改成功")
