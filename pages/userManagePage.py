# pages/userManagePage.py
import streamlit as st
import hashlib

from utils.auth_utils import require_role
from services.user_services import (
    get_all_users,
    create_user,
    update_user_role,
    soft_delete_user,
    get_ai_whitelist,
    add_ai_whitelist,
    remove_ai_whitelist,
)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def user_manage():
    # ===== 权限校验 =====
    require_role("admin")

    st.title("用户管理")
    st.caption(f"当前用户：{st.session_state['username']}（admin）")

    st.divider()

    # ===== 用户列表（合并 AI 权限管理）=====
    st.subheader("现有用户")

    users = get_all_users()
    ai_whitelist = set(get_ai_whitelist())

    col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([2, 2, 2, 2, 3])
    col_h1.markdown("**用户名**")
    col_h2.markdown("**角色**")
    col_h3.markdown("**AI助手**")
    col_h4.markdown("**操作**")
    col_h5.markdown("**管理**")

    if users:
        for uid, uname, urole, _ in users:
            is_admin = urole == "admin"
            enabled = is_admin or uid in ai_whitelist
            c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 3])
            c1.markdown(f"**{uname}**")
            c2.write(urole)
            if is_admin:
                c3.markdown("✅ 自动授权")
            elif enabled:
                c3.markdown("✅ 已授权")
            else:
                c3.markdown("❌ 未授权")
            with c4:
                if is_admin:
                    st.write("—")
                else:
                    if enabled:
                        if st.button("移出白名单", key=f"ai_rm_{uid}", type="secondary"):
                            remove_ai_whitelist(uid)
                            st.rerun()
                    else:
                        if st.button("加入白名单", key=f"ai_add_{uid}", type="primary"):
                            add_ai_whitelist(uid, st.session_state.get("user_id"))
                            st.rerun()
            with c5:
                if st.button("修改角色", key=f"edit_{uid}"):
                    st.session_state["edit_user"] = uid
                    st.rerun()
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
        default_idx = 0
        edit_uid = st.session_state.get("edit_user")
        if edit_uid in user_ids:
            default_idx = user_ids.index(edit_uid)
        selected_id = st.selectbox("选择用户 ID", user_ids, index=default_idx)
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
                    soft_delete_user(selected_id)
                    st.success("用户已删除")
                    st.rerun()
