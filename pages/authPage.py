# authPage.py
import streamlit as st

from services.user_services import authenticate


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

    col_welcome, col_role = st.columns([1, 3])
    with col_welcome:
        st.success(f"欢迎你，{username}")

    # ===== 权限提示 =====
    if role == "admin":
        info = "管理用户、管理试题"
    elif role == "editor":
        info = "管理试题"
    elif role == "viewer":
        info = "查看试题"
    with col_role:
        st.info(f"当前角色：**{role}**，你的权限：**{info}**")

    # ===== 退出 =====
    if st.button("退出登录"):
        for k in ["logged_in", "username", "role"]:
            st.session_state.pop(k, None)
        st.rerun()
