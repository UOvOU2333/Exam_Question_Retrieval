# pages/userManagePage.py
import streamlit as st
import hashlib

from utils.auth_utils import require_role
from services.user_services import (
    get_all_users,
    create_user,
    update_user_role,
    delete_user
)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def user_manage():
    # ===== 权限校验 =====
    require_role("admin")

    st.title("用户管理")
    st.caption(f"当前用户：{st.session_state['username']}（admin）")

    st.divider()

    # ===== 用户列表 =====
    st.subheader("现有用户")

    users = get_all_users()

    if users:
        st.table([
            {
                "ID": u[0],
                "用户名": u[1],
                "角色": u[2],
                "创建时间": u[3]
            }
            for u in users
        ])
    else:
        st.info("暂无用户")

    st.divider()

    # ===== 新增用户 =====
    st.subheader("新增用户")

    with st.form("add_user_form"):
        new_username = st.text_input("用户名")
        new_password = st.text_input("初始密码", type="password")
        new_role = st.selectbox("角色", ["admin", "editor", "viewer"])

        submitted = st.form_submit_button("创建用户")

        if submitted:
            if not new_username or not new_password:
                st.error("用户名和密码不能为空")
            else:
                try:
                    create_user(
                        new_username,
                        hash_password(new_password),
                        new_role
                    )
                    st.success("用户创建成功")
                    st.rerun()
                except Exception as e:
                    st.error(f"创建失败：{e}")

    st.divider()

    # ===== 修改 / 删除 =====
    st.subheader("修改 / 删除用户")

    user_ids = [u[0] for u in users]
    user_map = {u[0]: u for u in users}

    if user_ids:
        selected_id = st.selectbox("选择用户 ID", user_ids)
        selected_user = user_map[selected_id]

        st.write(f"用户名：**{selected_user[1]}**")

        new_role = st.selectbox(
            "修改角色",
            ["admin", "editor", "viewer"],
            index=["admin", "editor", "viewer"].index(selected_user[2])
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("更新角色"):
                update_user_role(selected_id, new_role)
                st.success("角色已更新")
                st.rerun()

        with col2:
            if st.button("删除用户"):
                if selected_user[1] == st.session_state["username"]:
                    st.error("不能删除当前登录用户")
                else:
                    delete_user(selected_id)
                    st.success("用户已删除")
                    st.rerun()
