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

    username = st.text_input("用户名")
    password = st.text_input("密码", type="password")

    if st.button("登录"):
        ok, role = authenticate(username, password)
        if ok:
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
    st.write(f"当前角色：**{role}**")

    st.divider()

    # ===== 权限提示 =====
    if role == "admin":
        st.info("你可以：管理用户、管理试题")
    elif role == "editor":
        st.info("你可以：管理试题")
    elif role == "viewer":
        st.info("你可以：查看试题")

    st.divider()

    # ===== 快捷入口（不是路由，只是 UX 提示）=====
    col1, col2, col3 = st.columns(3)

    with col1:
        st.button("🔍 题库检索", disabled=False)

    with col2:
        st.button(
            "🗂️ 试题管理",
            disabled=(role == "viewer")
        )

    with col3:
        if st.button(
            "👤 用户管理",
            disabled=(role != "admin")
        ):
            st.session_state["nav"] = "用户管理"
            st.rerun()

    st.divider()

    # ===== 退出 =====
    if st.button("退出登录"):
        for k in ["logged_in", "username", "role"]:
            st.session_state.pop(k, None)
        st.rerun()
