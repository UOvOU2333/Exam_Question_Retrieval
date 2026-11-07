# pages/userManagePage.py
import streamlit as st
import hashlib

from utils.auth_utils import require_permission
from utils.permissions import ALL_ROLES, ROLE_NAMES, is_admin, ROLE_EN_SHORT, can_be_authorized_for_record_agent
from services.user_services import (
    get_all_users_with_deleted,
    create_user,
    update_user_role,
    soft_delete_user,
    restore_user,
    delete_user,
    get_ai_whitelist,
    add_ai_whitelist,
    remove_ai_whitelist,
)
from services.record_agent_auth_services import (
    is_record_agent_enabled,
    grant_record_agent,
    revoke_record_agent,
    get_record_agent_whitelist,
)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


@st.dialog("确认永久删除", width="small")
def permanent_delete_confirm_dialog(uid, uname):
    st.warning(f"⚠️ 确定要永久删除用户 **{uname}**（ID {uid}）吗？此操作不可恢复！")

    col_c, col_d = st.columns(2)
    with col_c:
        if st.button("确定删除", type="primary", key=f"perm_del_ok_{uid}", use_container_width=True):
            try:
                delete_user(uid)
                st.success(f"用户 {uname} 已永久删除")
                st.rerun()
            except Exception as e:
                st.error(f"删除失败：{e}")
    with col_d:
        if st.button("取消", type="secondary", key=f"perm_del_no_{uid}", use_container_width=True):
            st.rerun()


def user_manage():
    # ===== 权限校验 =====
    require_permission("user_manage")

    st.title("用户管理")
    st.caption(f"当前用户：{st.session_state['username']}")

    col_list, col_edit = st.columns([3, 1])

    with col_list:
        with st.container(height=480):
            # ===== 用户列表（含已禁用用户 + AI 权限管理）=====
            st.subheader("现有用户")

            users = get_all_users_with_deleted()
            ai_whitelist = set(get_ai_whitelist())
            record_agent_whitelist = set(get_record_agent_whitelist())

            # 5 列布局：ID / 用户名 / 角色 / 状态 / 操作（操作列加宽容纳三组按钮）
            col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([1, 2, 2, 1.5, 4])
            col_h1.markdown("**ID**")
            col_h2.markdown("**用户名**")
            col_h3.markdown("**角色**")
            col_h4.markdown("**状态**")
            col_h5.markdown("**操作**")

            if users:
                for uid, uname, urole, _, is_deleted in users:
                    user_is_admin = is_admin(urole)
                    ai_enabled = user_is_admin or uid in ai_whitelist
                    ra_enabled = user_is_admin or uid in record_agent_whitelist
                    disabled = bool(is_deleted)
                    can_ra = can_be_authorized_for_record_agent(urole)

                    c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 1.5, 4])
                    c1.write(uid)
                    c2.markdown(f"**{uname}**")
                    c3.write(f"{ROLE_NAMES.get(urole, urole)}（{ROLE_EN_SHORT.get(urole,urole)}）")
                    if disabled:
                        c4.markdown(":gray[已禁用]")
                    else:
                        c4.markdown(":green[正常]")
                    with c5:
                        if disabled:
                            st.markdown("—")
                        else:
                            # 操作列内三组按钮并列：AI助手授权 | 录题Agent授权 | 修改角色
                            op_a, op_b, op_c = st.columns([1, 1, 1])
                            with op_a:
                                st.caption("AI助手")
                                if user_is_admin:
                                    st.markdown("自动授权")
                                elif ai_enabled:
                                    if st.button("取消授权", key=f"ai_rm_{uid}", type="secondary"):
                                        remove_ai_whitelist(uid)
                                        st.rerun()
                                else:
                                    if st.button("授权", key=f"ai_add_{uid}", type="primary"):
                                        add_ai_whitelist(uid, st.session_state.get("user_id"))
                                        st.rerun()
                            with op_b:
                                st.caption("录题Agent")
                                if user_is_admin:
                                    st.markdown("自动授权")
                                elif not can_ra:
                                    st.markdown(":gray[不可授权]")
                                elif ra_enabled:
                                    if st.button("取消授权", key=f"ra_rm_{uid}", type="secondary"):
                                        ok, msg = revoke_record_agent(uid, st.session_state.get("user_id"))
                                        if not ok:
                                            st.error(msg)
                                        st.rerun()
                                else:
                                    if st.button("授权", key=f"ra_add_{uid}", type="primary"):
                                        ok, msg = grant_record_agent(uid, st.session_state.get("user_id"))
                                        if not ok:
                                            st.error(msg)
                                        st.rerun()
                            with op_c:
                                st.caption("角色")
                                if st.button("修改角色", key=f"edit_{uid}"):
                                    st.session_state["edit_user"] = uid
                                    st.rerun()
                            
            else:
                st.info("暂无用户")

    st.divider()

    # ===== 新增用户 / 修改删除用户 并列 =====
    user_ids = [u[0] for u in users]
    user_map = {u[0]: u for u in users}

    st.subheader("新增用户")

    with st.form("add_user_form"):
        new_username = st.text_input("用户名")
        new_password = st.text_input("初始密码", type="password")
        new_role = st.selectbox("角色", list(ALL_ROLES), format_func=lambda r: ROLE_NAMES.get(r, r))

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

    with col_edit:
        st.subheader("修改用户")

        if user_ids:
            default_idx = 0
            edit_uid = st.session_state.get("edit_user")
            if edit_uid in user_ids:
                default_idx = user_ids.index(edit_uid)
            selected_id = st.selectbox("选择用户 ID", user_ids, index=default_idx)
            selected_user = user_map[selected_id]
            sel_uid, sel_uname, sel_urole, _, sel_is_deleted = selected_user
            sel_disabled = bool(sel_is_deleted)
            sel_is_admin = is_admin(sel_urole)
            sel_ai_enabled = sel_is_admin or sel_uid in ai_whitelist
            sel_ra_enabled = sel_is_admin or sel_uid in record_agent_whitelist
            sel_can_ra = can_be_authorized_for_record_agent(sel_urole)

            c_info, c_act = st.columns([3, 2])
            with c_info:
                st.markdown(f"**用户名：** {sel_uname}")
                st.markdown(f"**角色：** {ROLE_NAMES.get(sel_urole, sel_urole)}")
                if sel_disabled:
                    st.markdown("**状态：** :gray[已禁用]")
                else:
                    st.markdown("**状态：** :green[正常]")
            with c_act:
                if sel_disabled:
                    st.markdown("—")
                else:
                    # AI 助手授权
                    st.caption("AI助手授权")
                    if sel_is_admin:
                        st.info("自授权")
                    elif sel_ai_enabled:
                        if st.button("移除AI授权", key=f"edit_ai_rm_{sel_uid}", type="secondary"):
                            remove_ai_whitelist(sel_uid)
                            st.rerun()
                    else:
                        if st.button("新增AI授权", key=f"edit_ai_add_{sel_uid}", type="primary"):
                            add_ai_whitelist(sel_uid, st.session_state.get("user_id"))
                            st.rerun()
                    # 录题 Agent 授权
                    st.caption("录题AI授权")
                    if sel_is_admin:
                        st.info("自授权")
                    elif not sel_can_ra:
                        st.markdown(":gray[不可授权]")
                    elif sel_ra_enabled:
                        if st.button("取消录题授权", key=f"edit_ra_rm_{sel_uid}", type="secondary"):
                            ok, msg = revoke_record_agent(sel_uid, st.session_state.get("user_id"))
                            if not ok:
                                st.error(msg)
                            st.rerun()
                    else:
                        if st.button("授权录题AI", key=f"edit_ra_add_{sel_uid}", type="primary"):
                            ok, msg = grant_record_agent(sel_uid, st.session_state.get("user_id"))
                            if not ok:
                                st.error(msg)
                            st.rerun()

            new_role = st.selectbox(
                "修改角色",
                list(ALL_ROLES),
                index=list(ALL_ROLES).index(sel_urole),
                format_func=lambda r: ROLE_NAMES.get(r, r),
            )

            left_btn, right_btn = st.columns(2)

            with right_btn:
                if not sel_disabled:
                    with left_btn:
                        if st.button("更新角色", type="primary"):
                            update_user_role(selected_id, new_role)
                            st.success("角色已更新")
                            st.rerun()
                    if st.button("禁用用户", type="secondary", key=f"edit_disable_{sel_uid}"):
                        if sel_uname == st.session_state["username"]:
                            st.error("不能禁用当前登录用户")
                        else:
                            soft_delete_user(selected_id)
                            st.success("用户已禁用")
                            st.rerun()
                else:
                    if st.button("恢复用户", type="primary", key=f"edit_enable_{sel_uid}"):
                        restore_user(selected_id)
                        st.success("用户已恢复")
                        st.rerun()

            with st.expander("危险操作", expanded=False):
                st.warning(f"将删除用户 **{sel_uname}** ，此操作不可恢复。")
                if st.button("永久删除", type="secondary", key=f"edit_delete_{sel_uid}"):
                    if sel_uname == st.session_state["username"]:
                        st.error("不能删除当前登录用户")
                    else:
                        permanent_delete_confirm_dialog(selected_id, sel_uname)
                        st.success("用户已删除")
                        st.rerun()

        else:
            st.info("暂无用户可修改")
